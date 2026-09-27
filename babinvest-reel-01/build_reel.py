#!/usr/bin/env python3
"""
build_reel.py — générateur de Reels verticaux « face-less data » pour BabInvest.

Pipeline :
  1. Télécharge les visuels sources (ou réutilise ceux déjà présents dans sources/).
  2. Anime chaque image : DepthFlow (parallaxe 2.5D) si disponible, sinon Ken Burns
     (zoom lent 1.00 -> 1.08, recadrage 9:16 sans déformation).
  3. Compose texte / bandeaux / mentions / compteurs image par image (Pillow + numpy).
  4. Encode en H.264 1080x1920 30 fps + piste AAC silencieuse (ffmpeg).
  5. Génère la couverture, la légende et la planche contact de contrôle.

Usage :
  python3 build_reel.py                  # rendu final (exige toutes les sources réelles)
  python3 build_reel.py --no-depthflow   # force le fallback Ken Burns
  python3 build_reel.py --illustrations  # sans accès au site : scènes illustrées en calques
                                         # (parallaxe 2.5D natif), mention « Illustrations » ajoutée
  python3 build_reel.py --preview        # aperçu de mise en page : les sources manquantes
                                         # sont remplacées par des aplats neutres marqués
                                         # « SOURCE MANQUANTE » (jamais livrable)

Pour un autre Reel : dupliquez ce fichier et modifiez uniquement les blocs
CONFIG (SOURCES, SEGMENTS, CAPTION, COVER_*), le moteur reste identique.

Dépendances : python3 -m pip install pillow numpy   (+ optionnel : depthflow)
              ffmpeg / ffprobe dans le PATH
              polices Fraunces + Inter (Google Fonts, OFL) dans fonts/
"""
import argparse
import html
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))

# ════════════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════════════
W, H, FPS = 1080, 1920, 30
DURATION = 38.0
SAFE_TOP, SAFE_BOTTOM = 250, 380            # zones interdites au texte (UI Instagram)
SAFE_Y0, SAFE_Y1 = SAFE_TOP, H - SAFE_BOTTOM  # 250 .. 1540
MARGIN_X = 70                               # marge latérale du bandeau
PAD_X, PAD_Y = 44, 34                       # marge intérieure du bandeau

AUTHOR = "Karine Barmaki"
TITLE = "BabInvest — 7 quartiers de Marrakech classés par rendement"
OUT_BASENAME = "reel_babinvest_01"
COVER_NAME = "cover_babinvest_01.png"

# Couleurs
BAND_RGB, BAND_ALPHA = (0xEF, 0xE9, 0xDE), 0.90
GREEN = (0x1F, 0x4B, 0x3A)                  # noms de quartiers
TERRA = (0xA8, 0x55, 0x2F)                  # chiffres de rendement
MENTION_ALPHA = 0.70                        # mentions : #1F4B3A à 70 %

FONTS = {
    "serif": os.path.join(HERE, "fonts", "Fraunces-SemiBold.ttf"),
    "serif_bold": os.path.join(HERE, "fonts", "Fraunces-Bold.ttf"),
    "sans": os.path.join(HERE, "fonts", "Inter-Medium.ttf"),
    "sans_bold": os.path.join(HERE, "fonts", "Inter-SemiBold.ttf"),
}
EMOJI_FONT_CANDIDATES = [
    os.path.join(HERE, "fonts", "NotoColorEmoji.ttf"),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "C:/Windows/Fonts/seguiemj.ttf",
]

SITE = "https://maisonrecherchee.fr"
# nom local -> URL (None = résolu dynamiquement)
SOURCES = {
    "hero-home.webm": f"{SITE}/assets/video/hero-home.webm",
    "palmeraie.jpg": f"{SITE}/assets/img/guides/palmeraie/hero.jpg",
    "golfs.jpg": f"{SITE}/assets/img/guides/golfs-amelkis-al-maaden-royal-palm/hero.jpg",
    "ourika.jpg": f"{SITE}/assets/img/projets/wyld-ourika/01.jpg",
    "hivernage.jpg": f"{SITE}/assets/img/guides/hivernage/hero.jpg",
    "gueliz.jpg": f"{SITE}/assets/img/guides/gueliz/hero.jpg",
    "medina.jpg": f"{SITE}/assets/img/guides/medina/hero.jpg",
    "amizmiz.jpg": f"{SITE}/assets/img/projets/les-clos-de-leden/t1-01.jpg",
    "theone": None,  # 1re image de rendu de la page projet ci-dessous
}
THE_ONE_PAGE = f"{SITE}/projets/the-one-by-blackridge/"

# Point focal horizontal/vertical (0..1) pour le recadrage 9:16 « centré sur le sujet ».
# 0.5/0.5 = centre. Ajustez après avoir regardé les images (ex. "golfs.jpg": (0.4, 0.5)).
FOCUS = {}

MENTION_YIELD = "Rendement brut indicatif — source : guides BabInvest"
MENTION_RENDER = "Vue d'artiste — rendu non contractuel"
MENTION_ILLUS = "Illustrations stylisées — visuels non contractuels"

# Un segment = un plan. "cut": True -> coupe franche + flash blanc de 3 images à l'entrée.
# Lignes de texte : liste de runs (texte, style). Styles : name, price, yield, body, hook.
# Le style "yield" déclenche le compteur (0,6 s) sur les nombres du run.
SEGMENTS = [
    dict(t0=0.0, t1=2.5, src="hero-home.webm", motion="punchin", cut=False, layout="hook",
         lines=[[("Où acheter à Marrakech pour que ça rapporte ?", "hook")]]),
    dict(t0=2.5, t1=4.0, src="hero-home.webm", motion="punchin_cont", cut=False, layout="hook",
         lines=[[("7 zones. Prix/m² + rendement.", "hook")]]),
    dict(t0=4.0, t1=8.0, src="palmeraie.jpg", cut=True, mentions=[MENTION_YIELD],
         lines=[[("Palmeraie", "name")],
                [("22–38k MAD/m²", "price"), (" · ", "price"), ("6–9 %", "yield")]]),
    dict(t0=8.0, t1=12.0, src="golfs.jpg", cut=True, mentions=[MENTION_YIELD],
         lines=[[("Golfs", "name")],
                [("20–35k MAD/m²", "price"), (" · ", "price"), ("6–9 %", "yield")]]),
    dict(t0=12.0, t1=16.0, src="ourika.jpg", cut=True, mentions=[MENTION_YIELD, MENTION_RENDER],
         lines=[[("Route de l'Ourika", "name")],
                [("villa 2,5–6 M MAD", "price"), (" · ", "price"), ("6–9 %", "yield")],
                [("(longue durée)", "body")]]),
    dict(t0=16.0, t1=20.0, src="hivernage.jpg", cut=True, mentions=[MENTION_YIELD],
         lines=[[("Hivernage", "name")],
                [("16–24k MAD/m²", "price"), (" · ", "price"), ("7–11 %", "yield")]]),
    dict(t0=20.0, t1=24.0, src="gueliz.jpg", cut=True, mentions=[MENTION_YIELD],
         lines=[[("Guéliz", "name")],
                [("13–20k MAD/m²", "price"), (" · ", "price"), ("7–11 %", "yield")]]),
    dict(t0=24.0, t1=28.0, src="medina.jpg", cut=True, mentions=[MENTION_YIELD],
         lines=[[("🥇 Médina", "name")],
                [("2–5 M MAD à rénover", "price"), (" · ", "price"), ("9–13 %", "yield")],
                [("— gestion active obligatoire", "body")]]),
    dict(t0=28.0, t1=30.5, src="amizmiz.jpg", cut=True, mentions=[MENTION_RENDER], text_group="amz",
         lines=[[("Et la route d'Amizmiz ?", "name")],
                [("Prix pas encore publiés… 4 des 5 projets qu'on suit y sont.", "body")]]),
    dict(t0=30.5, t1=33.0, src="theone", cut=True, mentions=[MENTION_RENDER], text_group="amz",
         lines=[[("Et la route d'Amizmiz ?", "name")],
                [("Prix pas encore publiés… 4 des 5 projets qu'on suit y sont.", "body")]]),
    dict(t0=33.0, t1=38.0, src=None, motion="cta", cut=True, layout="cta",
         lines=[[("Commentez « AMIZMIZ » pour recevoir les chiffres 👇", "cta")]]),
]

# Planche contact : une image au milieu de chaque plan (11 images : le plan d'accroche est
# en 2 textes et le plan 28–33 s est scindé Amizmiz / The One, chaque moitié est contrôlée).
CONTACT_TIMES = [(s["t0"] + s["t1"]) / 2 for s in SEGMENTS]

COVER_SRC = "medina.jpg"
COVER_TITLE = "7 QUARTIERS DE MARRAKECH CLASSÉS PAR RENDEMENT"

CAPTION = """Prix au m² et rendement locatif brut, quartier par quartier. Données de nos guides, pas de promesses.
Le rendement élevé de la médina a un prix : la gestion. Et la route d'Amizmiz reste la grande inconnue.
👉 Commentez AMIZMIZ pour recevoir le détail des projets et le simulateur de rendement.
💾 Enregistrez ce Reel pour comparer avant d'acheter.
#immobiliermarrakech #investirmaroc #rendementlocatif #marrakech #immobilierMaroc #achatsurplan
"""

# ════════════════════════════════════════════════════════════════════════════
# Moteur
# ════════════════════════════════════════════════════════════════════════════
LOG = []


def log(msg):
    print(msg, flush=True)
    LOG.append(msg)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


# ── 1. Sources ──────────────────────────────────────────────────────────────
UA = {"User-Agent": "Mozilla/5.0 (BabInvest reel builder)"}


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def resolve_the_one():
    """Première image de rendu de la page projet The One (lecture seule)."""
    page = http_get(THE_ONE_PAGE).decode("utf-8", "replace")
    cands = re.findall(r'(?:src|data-src|href|content)="([^"]+\.(?:jpe?g|png|webp))"', page, re.I)
    cands = [html.unescape(c) for c in cands]
    # priorité aux images du dossier projet, dans l'ordre d'apparition dans la page
    proj = [c for c in cands if "/projets/" in c and "the-one" in c.lower()]
    pick = (proj or [c for c in cands if "/projets/" in c] or cands or [None])[0]
    if not pick:
        raise RuntimeError("aucune image trouvée sur la page The One")
    return urllib.parse.urljoin(THE_ONE_PAGE, pick)


def fetch_sources(src_dir):
    os.makedirs(src_dir, exist_ok=True)
    status = {}
    for name, url in SOURCES.items():
        existing = [f for f in os.listdir(src_dir) if os.path.splitext(f)[0] == os.path.splitext(name)[0]]
        if existing:
            status[name] = os.path.join(src_dir, existing[0])
            log(f"[source] {name}: déjà présent ({existing[0]})")
            continue
        try:
            if url is None:
                url = resolve_the_one()
                ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".jpg"
                dst = os.path.join(src_dir, name + ext)
            else:
                dst = os.path.join(src_dir, name)
            data = http_get(url)
            with open(dst, "wb") as f:
                f.write(data)
            status[name] = dst
            log(f"[source] {name}: téléchargé depuis {url} ({len(data)} o)")
        except Exception as e:  # noqa: BLE001
            status[name] = None
            log(f"[source] {name}: ÉCHEC du téléchargement ({url}) -> {e}")
    return status


def placeholder(name, path):
    """Aplat neutre pour l'aperçu de mise en page. N'est PAS une image de substitution."""
    img = Image.new("RGB", (1600, 2400), (96, 90, 84))
    d = ImageDraw.Draw(img)
    for y in range(0, 2400, 4):
        v = int(70 + 60 * y / 2400)
        d.line([(0, y), (1600, y)], fill=(v, v - 4, v - 8), width=4)
    for x in range(0, 1600, 200):
        d.line([(x, 0), (x, 2400)], fill=(120, 114, 108), width=2)
    for y in range(0, 2400, 200):
        d.line([(0, y), (1600, y)], fill=(120, 114, 108), width=2)
    f = ImageFont.truetype(FONTS["sans_bold"], 64)
    d.text((800, 520), "SOURCE MANQUANTE", font=f, fill=(255, 255, 255), anchor="mm")
    d.text((800, 610), name, font=f, fill=(255, 220, 160), anchor="mm")
    img.save(path)
    return path


# ── 2. Mouvement ────────────────────────────────────────────────────────────
def cover_crop_box(iw, ih, focus=(0.5, 0.5), zoom=1.0):
    """Boîte de recadrage 9:16 (sans déformation) autour du point focal, pour un zoom donné."""
    target = W / H
    if iw / ih > target:
        ch = ih
        cw = ih * target
    else:
        cw = iw
        ch = iw / target
    cw /= zoom
    ch /= zoom
    cx = min(max(focus[0] * iw, cw / 2), iw - cw / 2)
    cy = min(max(focus[1] * ih, ch / 2), ih - ch / 2)
    return cx - cw / 2, cy - ch / 2, cw, ch


def ease_in_out(x):
    return 0.5 - 0.5 * math.cos(math.pi * min(max(x, 0), 1))


def ease_out(x):
    x = min(max(x, 0), 1)
    return 1 - (1 - x) ** 3


def kenburns_frames(img, n, focus, z0=1.00, z1=1.08):
    """Ken Burns sub-pixel (transformation affine) : pas de tremblement type zoompan."""
    iw, ih = img.size
    for i in range(n):
        z = z0 + (z1 - z0) * (i / max(n - 1, 1))
        x, y, cw, ch = cover_crop_box(iw, ih, focus, z)
        s = cw / W
        frame = img.transform((W, H), Image.AFFINE, (s, 0, x, 0, s, y), resample=Image.BICUBIC)
        yield np.asarray(frame, dtype=np.uint8)


def depthflow_available():
    return shutil.which("depthflow") is not None


def depthflow_render(img_path, seconds, out_mp4):
    """Parallaxe 2.5D via DepthFlow. Retourne True si la vidéo a été produite."""
    cmds = [
        ["depthflow", "input", "-i", img_path, "main", "-o", out_mp4,
         "-w", str(W), "-h", str(H), "-f", str(FPS), "-t", str(seconds), "--ssaa", "1.5"],
        ["depthflow", "input", "-i", img_path, "main", "-o", out_mp4,
         "--width", str(W), "--height", str(H), "--fps", str(FPS), "--time", str(seconds)],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 10000:
                return True
        except Exception as e:  # noqa: BLE001
            err = getattr(e, "stderr", b"") or b""
            log(f"[depthflow] échec ({' '.join(cmd[:4])} …): {str(e)[:120]} {err.decode(errors='ignore')[-300:]}")
    return False


def video_frames(path, n, start=0.0, focus=(0.5, 0.5), zoom_fn=None):
    """Décode une vidéo, recadre en 9:16 (cover), applique un zoom par image."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", path],
                           capture_output=True, text=True, check=True).stdout.strip().split(",")
    iw, ih = int(probe[0]), int(probe[1])
    x, y, cw, ch = cover_crop_box(iw, ih, focus, 1.0)
    # sur-échantillonnage x1.25 pour que le punch-in reste net
    ow, oh = int(W * 1.25) // 2 * 2, int(H * 1.25) // 2 * 2
    vf = (f"fps={FPS},crop={int(cw)}:{int(ch)}:{int(x)}:{int(y)},scale={ow}:{oh}:flags=lanczos,"
          f"format=rgb24")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", path,
                          "-vf", vf, "-frames:v", str(n), "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    fsize = ow * oh * 3
    for i in range(n):
        buf = p.stdout.read(fsize)
        if len(buf) < fsize:
            break
        img = Image.frombuffer("RGB", (ow, oh), buf, "raw", "RGB", 0, 1)
        z = zoom_fn(i) if zoom_fn else 1.0
        cw2, ch2 = ow / z, oh / z
        s = cw2 / W
        frame = img.transform((W, H), Image.AFFINE, (s, 0, (ow - cw2) / 2, 0, s, (oh - ch2) / 2),
                              resample=Image.BICUBIC)
        yield np.asarray(frame, dtype=np.uint8)
    p.stdout.close()
    p.wait()


def mp4_frames(path, n):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf",
                          f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=rgb24",
                          "-frames:v", str(n), "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    last = None
    for _ in range(n):
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        last = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        yield last
    p.stdout.close()
    p.wait()


# ── 3. Texte ────────────────────────────────────────────────────────────────
_font_cache = {}


def font(key, size):
    k = (key, size)
    if k not in _font_cache:
        _font_cache[k] = ImageFont.truetype(FONTS[key], size)
    return _font_cache[k]


_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?")
_emoji_font = None


def emoji_img(ch, px):
    global _emoji_font
    if _emoji_font is None:
        for c in EMOJI_FONT_CANDIDATES:
            if os.path.exists(c):
                try:
                    _emoji_font = ImageFont.truetype(c, 109)
                    break
                except OSError:
                    pass
        if _emoji_font is None:
            raise RuntimeError("Police emoji introuvable (NotoColorEmoji.ttf) — placez-la dans fonts/")
    tmp = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((8, 8), ch, font=_emoji_font, embedded_color=True)
    tmp = tmp.crop(tmp.getbbox())
    r = px / tmp.height
    return tmp.resize((max(1, int(tmp.width * r)), px), Image.LANCZOS)


STYLE = {
    # style: (police, taille de base, couleur RGB, alpha)
    "hook": ("serif_bold", 92, GREEN, 1.0),
    "name": ("serif_bold", 96, GREEN, 1.0),
    "price": ("serif", 62, GREEN, 1.0),
    "yield": ("serif_bold", 62, TERRA, 1.0),
    "body": ("serif", 54, GREEN, 1.0),
    "cta": ("serif_bold", 66, GREEN, 1.0),
    "mention": ("sans", 30, GREEN, MENTION_ALPHA),
}


def split_emoji(text):
    out, pos = [], 0
    for m in _EMOJI_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def text_width(text, f, emoji_px):
    w = 0
    for chunk, is_emo in split_emoji(text):
        w += int(emoji_px * 1.05) if is_emo else f.getlength(chunk)
    return w


def wrap_words(text, f, maxw, emoji_px):
    """Retour à la ligne sans jamais séparer « ? », « % », « » », « 👇 » du mot précédent."""
    words = text.split(" ")
    glued = []
    for w in words:
        if glued and (w in ("?", "!", ":", ";", "%", "»", "…") or _EMOJI_RE.fullmatch(w)):
            glued[-1] += "\u00a0" + w
        elif glued and glued[-1] in ("«",):
            glued[-1] += "\u00a0" + w
        else:
            glued.append(w)
    lines, cur = [], ""
    for w in glued:
        t = (cur + " " + w) if cur else w
        if text_width(t.replace("\u00a0", " "), f, emoji_px) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return [ln.replace("\u00a0", " ") for ln in lines]


def counter_text(txt, progress):
    """Fait défiler chaque nombre du texte de 0 à sa valeur (progress 0..1)."""
    if progress >= 1:
        return txt

    def rep(m):
        s = m.group(0)
        dec = "," in s
        v = float(s.replace(",", "."))
        cur = v * ease_out(progress)
        return (f"{cur:.1f}".replace(".", ",")) if dec else str(int(round(cur)))
    return re.sub(r"\d+(?:,\d+)?", rep, txt)


class Block:
    """Bloc de texte pré-mis en page (lignes -> runs positionnés)."""

    def __init__(self, seg, maxw):
        self.rows = []  # [ [ (text, style, size) ... ], ... ]
        for line in seg["lines"]:
            if len(line) == 1:
                txt, st = line[0]
                fk, size, _, _ = STYLE[st]
                f = font(fk, size)
                for ln in wrap_words(txt, f, maxw, int(size * 0.9)):
                    self.rows.append([(ln, st, size)])
            else:
                # une ligne multi-runs : réduit la taille jusqu'à ce qu'elle tienne
                scale = 1.0
                while True:
                    w = sum(text_width(t, font(STYLE[s][0], int(STYLE[s][1] * scale)),
                                       int(STYLE[s][1] * scale * 0.9)) for t, s in line)
                    if w <= maxw or scale < 0.5:
                        break
                    scale -= 0.03
                self.rows.append([(t, s, int(STYLE[s][1] * scale)) for t, s in line])
        self.mentions = seg.get("mentions", [])

    def row_height(self, row):
        return int(max(sz for _, _, sz in row) * 1.18)

    def size(self):
        h = sum(self.row_height(r) for r in self.rows)
        w = 0
        for r in self.rows:
            w = max(w, sum(text_width(t, font(STYLE[s][0], sz), int(sz * 0.9)) for t, s, sz in r))
        mh = 0
        if self.mentions:
            mf = font("sans", STYLE["mention"][1])
            mh = 22 + len(self.mentions) * int(STYLE["mention"][1] * 1.45)
            w = max(w, max(mf.getlength(m) for m in self.mentions))
        return w, h, mh


def draw_runs(draw, canvas, x, y, row, counter_p):
    baseline_size = max(sz for _, _, sz in row)
    for txt, st, sz in row:
        fk, _, rgb, a = STYLE[st]
        f = font(fk, sz)
        if st == "yield":
            txt = counter_text(txt, counter_p)
        for chunk, is_emo in split_emoji(txt):
            if is_emo:
                px = int(sz * 0.9)
                em = emoji_img(chunk, px)
                canvas.alpha_composite(em, (int(x), int(y + baseline_size * 0.18)))
                x += int(px * 1.05)
            else:
                draw.text((x, y + (baseline_size - sz) * 0.8), chunk, font=f,
                          fill=rgb + (int(255 * a),))
                x += f.getlength(chunk)


def render_overlay(seg, t_local):
    """Calque RGBA (W x H) pour un segment à l'instant t_local."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    layout = seg.get("layout", "band")
    counter_p = min(t_local / 0.6, 1.0)

    if layout == "cta":
        # fond uni #EFE9DE + wordmark, léger zoom continu (aucune image figée)
        canvas.paste(BAND_RGB + (255,), (0, 0, W, H))
        z = 1.0 + 0.05 * (t_local / (seg["t1"] - seg["t0"]))
        wm_size = int(170 * z)
        fb = font("serif_bold", wm_size)
        wb, wi = fb.getlength("Bab"), fb.getlength("Invest")
        x0 = (W - (wb + wi)) / 2
        ywm = 760 - wm_size * 0.2
        draw.text((x0, ywm), "Bab", font=fb, fill=TERRA + (255,))
        draw.text((x0 + wb, ywm), "Invest", font=fb, fill=GREEN + (255,))
        blk = Block(seg, W - 2 * MARGIN_X - 2 * PAD_X)
        y = 1080
        for i, row in enumerate(blk.rows):
            rw = sum(text_width(t, font(STYLE[s][0], sz), int(sz * 0.9)) for t, s, sz in row)
            bob = 0
            if i == len(blk.rows) - 1:
                bob = 0  # le rebond est appliqué à l'emoji seul ci-dessous
            draw_runs_bounce(draw, canvas, (W - rw) / 2, y + bob, row, t_local)
            y += blk.row_height(row)
        return canvas

    blk = Block(seg, W - 2 * MARGIN_X - 2 * PAD_X)
    tw, th, mh = blk.size()
    bw = W - 2 * MARGIN_X
    bh = th + mh + 2 * PAD_Y
    if layout == "hook":
        by = int((SAFE_Y0 + SAFE_Y1) / 2 - bh / 2 - 60)
    else:
        by = SAFE_Y1 - 12 - bh          # bandeau calé en bas de la zone de sécurité
    by = max(by, SAFE_Y0)
    bx = MARGIN_X
    assert by >= SAFE_Y0 and by + bh <= SAFE_Y1, "texte hors zone de sécurité"
    band = Image.new("RGBA", (bw, bh), BAND_RGB + (int(255 * BAND_ALPHA),))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=26, fill=255)
    canvas.paste(band, (bx, by), mask)

    y = by + PAD_Y
    for row in blk.rows:
        if layout == "hook":
            rw = sum(text_width(t, font(STYLE[s][0], sz), int(sz * 0.9)) for t, s, sz in row)
            x = (W - rw) / 2
        else:
            x = bx + PAD_X
        draw_runs(draw, canvas, x, y, row, counter_p)
        y += blk.row_height(row)
    if blk.mentions:
        mfk, msz, mrgb, ma = STYLE["mention"]
        mf = font(mfk, msz)
        y = by + bh - PAD_Y - len(blk.mentions) * int(msz * 1.45) + 6
        for m in blk.mentions:
            draw.text((bx + PAD_X, y), m, font=mf, fill=mrgb + (int(255 * ma),))
            y += int(msz * 1.45)
    return canvas


def draw_runs_bounce(draw, canvas, x, y, row, t):
    """Comme draw_runs, avec un léger rebond sur les emojis (CTA)."""
    baseline_size = max(sz for _, _, sz in row)
    for txt, st, sz in row:
        fk, _, rgb, a = STYLE[st]
        f = font(fk, sz)
        for chunk, is_emo in split_emoji(txt):
            if is_emo:
                px = int(sz * 0.9)
                bob = int(10 * abs(math.sin(t * math.pi * 1.6)))
                canvas.alpha_composite(emoji_img(chunk, px), (int(x), int(y + baseline_size * 0.18 + bob)))
                x += int(px * 1.05)
            else:
                draw.text((x, y), chunk, font=f, fill=rgb + (int(255 * a),))
                x += f.getlength(chunk)


def check_safe(seg):
    """Vérifie le calque sur la 1re image : aucun pixel non transparent hors zone de sécurité."""
    if seg.get("layout") == "cta":
        ov = render_overlay(seg, seg["t1"] - seg["t0"])
        a = np.asarray(ov)
        # sur le CTA le fond est plein : on contrôle l'encre (pixels ≠ fond)
        ink = np.any(a[..., :3] != np.array(BAND_RGB), axis=2)
    else:
        a = np.asarray(render_overlay(seg, 1.0))
        ink = a[..., 3] > 0
    rows = np.where(ink.any(axis=1))[0]
    ok = rows.min() >= SAFE_Y0 and rows.max() < SAFE_Y1
    return ok, int(rows.min()), int(rows.max())


# ── 4. Assemblage ───────────────────────────────────────────────────────────
def segment_backgrounds(seg, src_paths, work, use_df, report):
    n = int(round((seg["t1"] - seg["t0"]) * FPS))
    src = seg["src"]
    if src is None:
        return (np.zeros((H, W, 3), np.uint8) for _ in range(n))
    path = src_paths[src]
    focus = FOCUS.get(src, (0.5, 0.5))
    if hasattr(path, "frame"):  # scène illustrée en calques (illustrations.py)
        scene = path
        if seg.get("motion", "").startswith("punchin"):
            t_off, total_hook = seg["t0"], SEGMENTS[1]["t1"]

            def gen_hook():
                for i in range(n):
                    t = t_off + i / FPS
                    z = 1.0 + 0.10 * ease_out(t / 0.5)
                    yield np.asarray(scene.frame(t / total_hook, zoom=z), dtype=np.uint8)
            report[src] = "illustration en calques : parallaxe 2.5D + punch-in"
            return gen_hook()

        def gen():
            for i in range(n):
                yield np.asarray(scene.frame(i / max(n - 1, 1)), dtype=np.uint8)
        report[src] = "illustration en calques : parallaxe 2.5D (zoom 1.00→1.08)"
        return gen()
    if path.endswith((".webm", ".mp4", ".mov")):
        t_off = seg["t0"]
        total_hook = SEGMENTS[1]["t1"]

        def zoom(i, t_off=t_off):
            t = t_off + i / FPS
            # punch-in rapide (0,5 s, 1.00 -> 1.12) puis dérive lente jusqu'à 1.18
            return 1.0 + 0.12 * ease_out(t / 0.5) + 0.06 * (t / total_hook)
        report[seg["src"]] = "vidéo native + punch-in"
        return video_frames(path, n, start=t_off, focus=focus, zoom_fn=zoom)

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if use_df:
        out = os.path.join(work, f"df_{os.path.splitext(os.path.basename(path))[0]}_{seg['t0']:.1f}.mp4")
        if depthflow_render(path, seg["t1"] - seg["t0"], out):
            report[src] = "DepthFlow"
            return mp4_frames(out, n)
        log(f"[motion] {src}: DepthFlow indisponible/échec -> fallback Ken Burns")
    report[src] = "Ken Burns 1.00→1.08"
    return kenburns_frames(img, n, focus)


def build_video(src_paths, out_dir, use_df, tag=""):
    work = os.path.join(out_dir, ".work")
    os.makedirs(work, exist_ok=True)
    out_mp4 = os.path.join(out_dir, f"{OUT_BASENAME}{tag}.mp4")
    for seg in SEGMENTS:
        ok, y0, y1 = check_safe(seg)
        log(f"[safe] {seg['t0']:>4.1f}-{seg['t1']:<4.1f}s texte y={y0}..{y1} "
            f"(zone autorisée {SAFE_Y0}..{SAFE_Y1 - 1}) {'OK' if ok else 'HORS ZONE'}")
        if not ok:
            raise SystemExit("Texte hors zone de sécurité — ajustez la mise en page.")

    enc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-map", "0:v", "-map", "1:a", "-shortest",
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 2),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-metadata", f"title={TITLE}", "-metadata", f"artist={AUTHOR}",
        "-metadata", f"author={AUTHOR}", "-metadata", f"composer={AUTHOR}",
        "-metadata", f"comment=BabInvest — {AUTHOR}",
        out_mp4], stdin=subprocess.PIPE)

    report = {}
    total = int(round(DURATION * FPS))
    written = 0
    overlay_cache = {}
    for seg in SEGMENTS:
        n = int(round((seg["t1"] - seg["t0"]) * FPS))
        bg_iter = segment_backgrounds(seg, src_paths, work, use_df, report)
        group = seg.get("text_group")
        # temps local du texte : continu à travers les plans d'un même groupe
        g_t0 = min(s["t0"] for s in SEGMENTS if s.get("text_group") == group) if group else seg["t0"]
        last_bg = None
        for i in range(n):
            bg = next(bg_iter, None)
            if bg is None:
                bg = last_bg
            last_bg = bg
            t_local = seg["t0"] + i / FPS - g_t0
            animated = (t_local < 0.6) or seg.get("layout") == "cta"
            key = (id(seg) if not group else group, "anim" if animated else "static")
            if animated or key not in overlay_cache:
                ov = render_overlay(seg, t_local)
                a = np.asarray(ov, dtype=np.float32)
                cached = (a[..., :3], a[..., 3:4] / 255.0)
                if not animated:
                    overlay_cache[key] = cached
            else:
                cached = overlay_cache[key]
            rgb, alpha = cached
            frame = bg.astype(np.float32) * (1 - alpha) + rgb * alpha
            # flash blanc léger sur les 3 premières images après une coupe franche
            if seg.get("cut") and i < 3:
                k = (0.55, 0.35, 0.15)[i]
                frame = frame * (1 - k) + 255 * k
            enc.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
            written += 1
        log(f"[render] {seg['t0']:>4.1f}-{seg['t1']:<4.1f}s {seg['src'] or 'CTA'} ({n} images)")
    assert written == total, (written, total)
    enc.stdin.close()
    enc.wait()
    if enc.returncode:
        raise SystemExit("ffmpeg a échoué")
    shutil.rmtree(work, ignore_errors=True)
    return out_mp4, report


# ── 5. Couverture, légende, planche contact ────────────────────────────────
def build_cover(src_paths, out_path, preview_mark=False):
    src = src_paths[COVER_SRC]
    if hasattr(src, "still"):
        img = src.still().convert("RGBA")
    else:
        img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        x, y, cw, ch = cover_crop_box(*img.size, FOCUS.get(COVER_SRC, (0.5, 0.5)), 1.0)
        img = img.resize((W, H), Image.LANCZOS, box=(x, y, x + cw, y + ch)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # titre dans la zone centrale 4:5 (visible dans la grille du profil)
    words = COVER_TITLE.split(" ")
    size = 132
    maxw = W - 2 * MARGIN_X - 2 * PAD_X
    while True:
        f = font("serif_bold", size)
        lines = wrap_words(COVER_TITLE, f, maxw, size)
        if max(f.getlength(l) for l in lines) <= maxw and len(lines) <= 5:
            break
        size -= 4
    lh = int(size * 1.08)
    bh = lh * len(lines) + 2 * PAD_Y + 20
    by = int(H / 2 - bh / 2)
    band = Image.new("RGBA", (W - 2 * MARGIN_X, bh), BAND_RGB + (int(255 * BAND_ALPHA),))
    mask = Image.new("L", band.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, band.width - 1, bh - 1], radius=30, fill=255)
    ov.paste(band, (MARGIN_X, by), mask)
    yy = by + PAD_Y + 6
    for i, ln in enumerate(lines):
        col = TERRA if "RENDEMENT" in ln else GREEN
        d.text((W / 2, yy), ln, font=f, fill=col + (255,), anchor="ma")
        yy += lh
    if preview_mark:
        d.text((W / 2, 300), "APERÇU — SOURCE MANQUANTE", font=font("sans_bold", 40),
               fill=(255, 255, 255, 255), anchor="mm")
    Image.alpha_composite(img, ov).convert("RGB").save(out_path)
    del words
    return out_path


def build_contact_sheet(mp4, out_path):
    thumbs = []
    tw, th = 360, 640
    for t in CONTACT_TIMES:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", mp4, "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        im = Image.frombuffer("RGB", (W, H), raw, "raw", "RGB", 0, 1).copy()
        d = ImageDraw.Draw(im, "RGBA")
        # repères des zones de sécurité (sur la planche uniquement)
        d.rectangle([0, 0, W, SAFE_TOP], fill=(255, 0, 0, 60))
        d.rectangle([0, H - SAFE_BOTTOM, W, H], fill=(255, 0, 0, 60))
        d.line([(0, SAFE_TOP), (W, SAFE_TOP)], fill=(255, 0, 0, 255), width=4)
        d.line([(0, H - SAFE_BOTTOM), (W, H - SAFE_BOTTOM)], fill=(255, 0, 0, 255), width=4)
        d.text((24, 40), f"t = {t:.2f} s", font=font("sans_bold", 64), fill=(255, 255, 255, 255),
               stroke_width=4, stroke_fill=(0, 0, 0, 255))
        thumbs.append(im.resize((tw, th), Image.LANCZOS))
    cols = 4 if len(thumbs) > 10 else 5
    rows = math.ceil(len(thumbs) / cols)
    gap = 16
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * gap, rows * th + (rows + 1) * gap), (30, 30, 30))
    for i, im in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(im, (gap + c * (tw + gap), gap + r * (th + gap)))
    sheet.save(out_path)
    return out_path


def ffprobe_summary(mp4):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "format=duration,size,bit_rate:format_tags=title,artist:"
                           "stream=index,codec_type,codec_name,profile,width,height,r_frame_rate,"
                           "pix_fmt,sample_rate,channels",
                           "-of", "default=noprint_wrappers=1", mp4],
                          capture_output=True, text=True, check=True).stdout


# ── main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=HERE, help="dossier de sortie (défaut : dossier du script)")
    ap.add_argument("--sources", default=os.path.join(HERE, "sources"),
                    help="dossier des visuels sources (téléchargés ou déposés à la main)")
    ap.add_argument("--no-depthflow", action="store_true", help="forcer le fallback Ken Burns")
    ap.add_argument("--illustrations", action="store_true",
                    help="remplacer les visuels du site par des scènes illustrées stylisées (illustrations.py) "
                         "+ mention « Illustrations » à l'écran")
    ap.add_argument("--preview", action="store_true",
                    help="aperçu de mise en page avec aplats pour les sources manquantes (non livrable)")
    args = ap.parse_args()

    for k, p in FONTS.items():
        if not os.path.exists(p):
            raise SystemExit(f"Police manquante : {p} (Fraunces / Inter, Google Fonts)")

    if args.illustrations:
        from illustrations import Scene
        status = {k: Scene(k) for k in SOURCES}
        for seg in SEGMENTS:
            if seg["src"] is not None:
                seg["mentions"] = seg.get("mentions", []) + [MENTION_ILLUS]
        log("[source] mode --illustrations : scènes illustrées stylisées (illustrations.py), "
            "aucune photo du site utilisée")
    else:
        status = fetch_sources(args.sources)
    missing = [k for k, v in status.items() if v is None]
    out_dir = args.out
    tag = ""
    if missing:
        if not args.preview:
            raise SystemExit(f"Sources manquantes : {', '.join(missing)}. Déposez-les dans {args.sources} "
                             f"(mêmes noms) ou relancez avec --preview pour un simple aperçu de mise en page.")
        out_dir = os.path.join(args.out, "preview")
        os.makedirs(out_dir, exist_ok=True)
        ph_dir = os.path.join(out_dir, ".placeholders")
        os.makedirs(ph_dir, exist_ok=True)
        tag = "_APERCU"
        for k in missing:
            if k.endswith(".webm"):
                png = placeholder(k, os.path.join(ph_dir, k + ".png"))
                mp4 = os.path.join(ph_dir, k + ".mp4")
                run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", png, "-t", "5", "-r", str(FPS),
                     "-vf", "scale=1600:2400,format=yuv420p", mp4])
                status[k] = mp4
            else:
                status[k] = placeholder(k, os.path.join(ph_dir, k + ".png"))
        log(f"[preview] aplats « SOURCE MANQUANTE » pour : {', '.join(missing)}")

    use_df = (not args.no_depthflow) and (not args.illustrations) and depthflow_available()
    if not args.no_depthflow and not args.illustrations and not use_df:
        log("[motion] DepthFlow non installé -> fallback Ken Burns pour toutes les images")

    mp4, report = build_video(status, out_dir, use_df, tag)
    cover = build_cover(status, os.path.join(out_dir, COVER_NAME.replace(".png", f"{tag}.png")), bool(missing))
    with open(os.path.join(out_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(CAPTION)
    sheet = build_contact_sheet(mp4, os.path.join(out_dir, f"contact_sheet{tag}.png"))

    log("\n=== Animation par source ===")
    for k, v in report.items():
        log(f"  {k:<16} {v}")
    log("\n=== ffprobe ===\n" + ffprobe_summary(mp4))
    log("=== Fichiers ===")
    for p in [mp4, cover, os.path.join(out_dir, "caption.txt"), sheet, os.path.abspath(__file__)]:
        log(f"  {os.path.getsize(p):>10,d} o  {os.path.relpath(p, args.out)}")
    with open(os.path.join(out_dir, f"build_log{tag}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG) + "\n")


if __name__ == "__main__":
    sys.exit(main())
