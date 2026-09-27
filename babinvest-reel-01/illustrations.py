"""
illustrations.py — scènes illustrées stylisées (dessin vectoriel procédural, Pillow + numpy)
utilisées quand les visuels du site ne sont pas disponibles.

Chaque scène = pile de calques RGBA (du fond vers l'avant-plan) avec une profondeur 0..1.
L'animation décale / zoome chaque calque selon sa profondeur : vrai parallaxe 2.5D,
sans modèle de profondeur. Aucune photo, aucune image générée par IA : tout est dessiné ici.
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
CW, CH = 1240, 2204          # calques plus grands que l'image : marge pour le mouvement
SS = 2                       # sur-échantillonnage (anti-crénelage)

# Palette « Marrakech » accordée à la charte BabInvest
SKY_TOP = (238, 196, 150)
SKY_LOW = (247, 226, 196)
SKY_BLUE_TOP = (150, 188, 214)
SUN = (255, 238, 205)
ATLAS = (150, 128, 140)
SNOW = (246, 240, 236)
TERRA = (192, 100, 62)
TERRA_D = (160, 78, 48)
OCHRE = (214, 158, 98)
PINK = (214, 136, 108)
PINK_L = (230, 160, 128)
SAND = (228, 206, 170)
GREEN = (31, 75, 58)
PALM = (46, 84, 58)
OLIVE = (122, 134, 92)
LAWN = (104, 150, 82)
LAWN_L = (132, 174, 96)
WHITE = (246, 242, 234)
GLASS = (70, 104, 128)
GLASS_L = (130, 170, 190)
POOL = (86, 176, 190)
WOOD = (150, 104, 70)
JACARANDA = (150, 120, 190)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Layer:
    """Calque dessiné en coordonnées normalisées (u,v) ∈ [0,1]²."""

    def __init__(self, depth, haze=0.0, haze_col=SKY_LOW):
        self.depth = depth
        self.haze = haze
        self.haze_col = haze_col
        self.img = Image.new("RGBA", (CW * SS, CH * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def c(self, col):
        col = mix(col, self.haze_col, self.haze)
        return col + (255,)

    def P(self, u, v):
        return (u * CW * SS, v * CH * SS)

    def poly(self, pts, col):
        self.d.polygon([self.P(u, v) for u, v in pts], fill=self.c(col))

    def rect(self, u0, v0, u1, v1, col):
        self.d.rectangle([self.P(u0, v0), self.P(u1, v1)], fill=self.c(col))

    def rrect(self, u0, v0, u1, v1, r, col):
        self.d.rounded_rectangle([self.P(u0, v0), self.P(u1, v1)], radius=r * CW * SS, fill=self.c(col))

    def ellipse(self, u, v, ru, rv, col):
        self.d.ellipse([self.P(u - ru, v - rv), self.P(u + ru, v + rv)], fill=self.c(col))

    def line(self, pts, col, w):
        self.d.line([self.P(u, v) for u, v in pts], fill=self.c(col), width=int(w * CW * SS), joint="curve")

    def final(self):
        return self.img.resize((CW, CH), Image.LANCZOS)


# ── primitives ──────────────────────────────────────────────────────────────
def sky(top, low, sun=None):
    y = np.linspace(0, 1, CH)[:, None]
    t = np.clip(y / 0.62, 0, 1) ** 0.9
    arr = np.array(top)[None, None, :] * (1 - t[..., None]) + np.array(low)[None, None, :] * t[..., None]
    arr = np.repeat(arr, CW, axis=1)
    if sun:
        su, sv, sr = sun
        yy, xx = np.mgrid[0:CH, 0:CW]
        dist = np.hypot(xx - su * CW, yy - sv * CH) / (sr * CW)
        glow = np.clip(1 - dist / 5, 0, 1) ** 2 * 0.55
        disk = np.clip((1.02 - dist) * 25, 0, 1)
        k = np.maximum(glow, disk)[..., None]
        arr = arr * (1 - k) + np.array(SUN) * k
    img = Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
    return img


def ridge(seed, base, amp, n=240, rough=1.0):
    rnd = random.Random(seed)
    comps = [(rnd.uniform(0.6, 1.6) * f, rnd.uniform(0, 6.28), 1 / f ** 1.1)
             for f in (1, 2.3, 4.7, 9.1, 17.3)]
    us = [i / (n - 1) * 1.0 for i in range(n)]
    vs = []
    for u in us:
        s = sum(a * math.sin(u * fr * math.pi * 2 + ph) * (rough if a < 0.3 else 1) for fr, ph, a in comps)
        vs.append(base - amp * (0.5 + 0.5 * s / 1.9))
    return list(zip(us, vs))


def mountains(L, seed, base, amp, col, snow_line=None):
    pts = ridge(seed, base, amp)
    L.poly([(0, 1.0)] + pts + [(1, 1.0)], col)
    if snow_line is not None:
        # neige : tout ce qui dépasse snow_line (masque numpy sur le calque)
        a = np.array(L.img)
        yy = np.arange(a.shape[0])[:, None] / (CH * SS)
        xx = np.arange(a.shape[1])[None, :] / (CW * SS)
        wob = 0.006 * np.sin(xx * 60) + 0.004 * np.sin(xx * 143)
        m = (a[..., 3] > 0) & (yy < snow_line + wob)
        sc = np.array(L.c(SNOW)[:3])
        a[m, :3] = sc
        # ombrage latéral sur la neige
        L.img = Image.fromarray(a, "RGBA")
        L.d = ImageDraw.Draw(L.img)


def ground(L, v, col, wav=0.006, seed=1):
    rnd = random.Random(seed)
    ph = rnd.uniform(0, 6)
    pts = [(u / 60, v + wav * math.sin(u / 60 * 9 + ph)) for u in range(61)]
    L.poly([(0, 1.0)] + pts + [(1, 1.0)], col)


def palm(L, u, v, h, lean=0.0, col=PALM, trunk=WOOD, seed=0):
    """Palmier : tronc courbe effilé + palmes tombantes. (u,v) = pied, h = hauteur (en v)."""
    rnd = random.Random(seed)
    asp = CH / CW
    n = 14
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((u + lean * t * t * h / asp, v - t * h))
    tw = 0.010 * (h / 0.25)
    left = [(x - tw * (1 - 0.45 * i / n), y) for i, (x, y) in enumerate(pts)]
    right = [(x + tw * (1 - 0.45 * i / n), y) for i, (x, y) in enumerate(pts)]
    L.poly(left + right[::-1], mix(trunk, (60, 44, 30), 0.3))
    for i in range(1, n, 2):  # anneaux du stipe
        x, y = pts[i]
        L.line([(x - tw * 0.9, y), (x + tw * 0.9, y + 0.002)], mix(trunk, (40, 30, 20), 0.5), 0.0016 * (h / 0.25))
    cx, cy = pts[-1]
    fr = h * 0.42
    for k in range(11):
        ang = -math.pi / 2 + (k - 5) * 0.33 + rnd.uniform(-0.1, 0.1)
        droop = 0.55 + rnd.uniform(0, 0.35)
        leaf = []
        m = 12
        for j in range(m + 1):
            t = j / m
            dx = math.cos(ang) * fr * t
            dy = math.sin(ang) * fr * t + droop * fr * t * t
            wdt = fr * 0.10 * math.sin(math.pi * t)
            nx, ny = -math.sin(ang), math.cos(ang)
            leaf.append((cx + dx / asp + nx * wdt / asp, cy + dy + ny * wdt))
        for j in range(m, -1, -1):
            t = j / m
            dx = math.cos(ang) * fr * t
            dy = math.sin(ang) * fr * t + droop * fr * t * t
            wdt = fr * 0.10 * math.sin(math.pi * t)
            nx, ny = -math.sin(ang), math.cos(ang)
            leaf.append((cx + dx / asp - nx * wdt / asp, cy + dy - ny * wdt))
        L.poly(leaf, mix(col, (20, 40, 28), rnd.uniform(0, 0.35)))
    L.ellipse(cx, cy, 0.008 * h / 0.25, 0.005 * h / 0.25, mix(col, (20, 30, 20), 0.5))


def blob_tree(L, u, v, r, col, seed=0):
    rnd = random.Random(seed)
    asp = CH / CW
    L.rect(u - 0.004, v - r * 0.6, u + 0.004, v, mix(WOOD, (50, 40, 30), 0.4))
    for _ in range(9):
        du = rnd.uniform(-r, r) * 0.9 / asp * 1.4
        dv = rnd.uniform(-r, r * 0.3) * 0.8
        rr = r * rnd.uniform(0.45, 0.7)
        L.ellipse(u + du, v - r * 1.1 + dv, rr / asp * 1.4, rr, mix(col, (30, 40, 30), rnd.uniform(0, 0.3)))


def box_house(L, u0, v_base, w, h, col, win_col=(90, 60, 50), rnd=None, terrace=True):
    rnd = rnd or random.Random(0)
    L.rect(u0, v_base - h, u0 + w, v_base, col)
    L.rect(u0 + w * 0.82, v_base - h, u0 + w, v_base, mix(col, (60, 30, 20), 0.18))  # ombre
    if terrace:
        L.rect(u0 - 0.002, v_base - h - 0.004, u0 + w + 0.002, v_base - h, mix(col, (255, 240, 220), 0.25))
    nx = max(1, int(w / 0.03))
    ny = max(1, int(h / 0.03))
    for i in range(nx):
        for j in range(ny):
            if rnd.random() < 0.55:
                x = u0 + (i + 0.5) * w / nx
                y = v_base - h + (j + 0.55) * h / ny
                L.rrect(x - 0.005, y - 0.006, x + 0.005, y + 0.006, 0.003, win_col)


def minaret(L, u, v_base, h, col=OCHRE):
    w = h * 0.12
    L.rect(u - w / 2, v_base - h, u + w / 2, v_base, col)
    L.rect(u + w * 0.2, v_base - h, u + w / 2, v_base, mix(col, (80, 40, 20), 0.2))
    # décor en arcs
    for k in range(3):
        y = v_base - h * (0.45 + 0.17 * k)
        L.rrect(u - w * 0.28, y - h * 0.05, u + w * 0.28, y + h * 0.05, 0.004, mix(col, (90, 50, 30), 0.35))
    L.rect(u - w * 0.62, v_base - h - h * 0.02, u + w * 0.62, v_base - h + h * 0.03, mix(col, (255, 230, 200), 0.2))
    for k in range(5):  # merlons
        x = u - w * 0.6 + k * w * 0.3
        L.rect(x, v_base - h - h * 0.05, x + w * 0.14, v_base - h - h * 0.02, col)
    lw = w * 0.45
    L.rect(u - lw / 2, v_base - h * 1.2, u + lw / 2, v_base - h * 1.02, col)
    L.poly([(u - lw * 0.6, v_base - h * 1.2), (u, v_base - h * 1.27), (u + lw * 0.6, v_base - h * 1.2)], TERRA_D)
    L.line([(u, v_base - h * 1.27), (u, v_base - h * 1.36)], (200, 170, 90), 0.002)
    for k in range(3):
        L.ellipse(u, v_base - h * (1.29 + 0.025 * k), 0.004 - k * 0.0008, 0.0025 - k * 0.0005, (220, 180, 80))


def pool(L, u0, v0, u1, v1):
    L.rrect(u0, v0, u1, v1, 0.01, POOL)
    for k in range(4):
        y = v0 + (k + 1) * (v1 - v0) / 5
        L.line([(u0 + 0.02, y), (u1 - 0.02, y + 0.002)], (170, 225, 230), 0.0018)


def modern_villa(L, u0, v_base, w, h):
    # volumes blancs en porte-à-faux, grandes baies, bardage bois
    L.rect(u0, v_base - h * 0.55, u0 + w, v_base, WHITE)
    L.rect(u0 + w * 0.08, v_base - h * 0.45, u0 + w * 0.62, v_base - h * 0.05, GLASS)
    for k in range(5):
        x = u0 + w * 0.08 + k * w * 0.11
        L.line([(x, v_base - h * 0.45), (x, v_base - h * 0.05)], GLASS_L, 0.0015)
    L.rect(u0 + w * 0.66, v_base - h * 0.45, u0 + w * 0.92, v_base - h * 0.05, WOOD)
    for k in range(9):
        x = u0 + w * 0.67 + k * w * 0.028
        L.line([(x, v_base - h * 0.45), (x, v_base - h * 0.05)], mix(WOOD, (60, 40, 25), 0.4), 0.0012)
    L.rect(u0 + w * 0.25, v_base - h, u0 + w * 1.08, v_base - h * 0.55, WHITE)
    L.rect(u0 + w * 0.30, v_base - h * 0.92, u0 + w * 1.0, v_base - h * 0.62, GLASS)
    L.rect(u0 + w * 0.25, v_base - h * 0.57, u0 + w * 1.08, v_base - h * 0.55, mix(WHITE, (0, 0, 0), 0.25))
    L.rect(u0 + w * 0.22, v_base - h * 1.02, u0 + w * 1.11, v_base - h, mix(WHITE, (0, 0, 0), 0.08))


def tower(L, u0, v_base, w, h, floors=22, col=WHITE):
    L.rect(u0, v_base - h, u0 + w, v_base, col)
    L.rect(u0 + w * 0.78, v_base - h, u0 + w, v_base, mix(col, (40, 50, 60), 0.2))
    fh = h / floors
    for f in range(floors):
        y = v_base - h + f * fh
        L.rect(u0 + w * 0.05, y + fh * 0.22, u0 + w * 0.95, y + fh * 0.78, GLASS if f % 2 == 0 else mix(GLASS, GLASS_L, 0.35))
        L.rect(u0 - w * 0.03, y + fh * 0.78, u0 + w * 1.03, y + fh * 0.92, mix(col, (255, 255, 255), 0.3))
        L.rect(u0 + w * 0.60, y + fh * 0.22, u0 + w * 0.66, y + fh * 0.78, WOOD)
    L.rect(u0 - w * 0.05, v_base - h - fh * 0.5, u0 + w * 1.05, v_base - h, mix(col, (0, 0, 0), 0.08))


def birds(L, seed, n, u0, u1, v0, v1):
    rnd = random.Random(seed)
    for _ in range(n):
        u, v, s = rnd.uniform(u0, u1), rnd.uniform(v0, v1), rnd.uniform(0.006, 0.011)
        L.line([(u - s, v - s * 0.3), (u, v), (u + s, v - s * 0.35)], (90, 70, 70), 0.0018)


def cloud(L, u, v, s, col=(255, 246, 236)):
    for du, dv, r in ((0, 0, 1), (-0.9, 0.25, 0.7), (0.9, 0.2, 0.75), (0.4, -0.35, 0.7), (-0.4, -0.25, 0.6)):
        L.ellipse(u + du * s, v + dv * s * 0.55, r * s, r * s * 0.55, col)


# ── scènes ──────────────────────────────────────────────────────────────────
def scene_skyline():
    bg = sky(SKY_TOP, SKY_LOW, sun=(0.70, 0.30, 0.055))
    far = Layer(0.05, 0.35)
    mountains(far, 3, 0.47, 0.13, ATLAS, snow_line=0.385)
    mid = Layer(0.35)
    rnd = random.Random(5)
    ground(mid, 0.53, PINK, seed=2)
    u = -0.02
    while u < 1.02:
        w = rnd.uniform(0.05, 0.11)
        box_house(mid, u, 0.56, w, rnd.uniform(0.03, 0.08), mix(PINK, PINK_L, rnd.random()), rnd=rnd)
        u += w * rnd.uniform(0.7, 1.0)
    minaret(mid, 0.26, 0.54, 0.26)
    near = Layer(0.7)
    # remparts crénelés
    near.rect(0, 0.62, 1, 1.0, TERRA)
    for k in range(40):
        near.rect(k / 40, 0.605, k / 40 + 0.014, 0.622, TERRA)
    near.rect(0, 0.62, 1, 0.625, TERRA_D)
    near.rrect(0.44, 0.66, 0.56, 0.78, 0.05, TERRA_D)  # porte (Bab)
    fg = Layer(1.0)
    palm(fg, 0.05, 1.0, 0.52, lean=0.05, seed=1)
    palm(fg, 0.93, 1.0, 0.46, lean=-0.06, seed=2)
    palm(fg, 0.82, 1.0, 0.33, lean=0.03, seed=3)
    birds(far, 4, 6, 0.45, 0.8, 0.18, 0.28)
    return bg, [far, mid, near, fg]


def scene_palmeraie():
    bg = sky(SKY_BLUE_TOP, SKY_LOW, sun=(0.25, 0.22, 0.05))
    far = Layer(0.05, 0.4)
    mountains(far, 11, 0.45, 0.12, ATLAS, snow_line=0.37)
    l2 = Layer(0.3, 0.25)
    ground(l2, 0.50, SAND, seed=4)
    rnd = random.Random(8)
    for i in range(16):
        palm(l2, rnd.uniform(0, 1), 0.52 + rnd.uniform(0, 0.02), rnd.uniform(0.10, 0.15),
             lean=rnd.uniform(-0.05, 0.05), seed=i)
    l3 = Layer(0.55)
    ground(l3, 0.56, (218, 190, 150), seed=5)
    box_house(l3, 0.52, 0.60, 0.26, 0.055, OCHRE, rnd=random.Random(3))   # villa basse
    box_house(l3, 0.60, 0.555, 0.12, 0.04, mix(OCHRE, PINK, 0.3), rnd=random.Random(4))
    pool(l3, 0.54, 0.605, 0.76, 0.63)
    fg = Layer(1.0)
    for i, (u, h, ln) in enumerate([(0.06, 0.58, 0.06), (0.25, 0.44, -0.02), (0.78, 0.50, -0.05), (0.97, 0.62, -0.03)]):
        palm(fg, u, 1.0, h, lean=ln, seed=20 + i)
    return bg, [far, l2, l3, fg]


def scene_golfs():
    bg = sky(SKY_BLUE_TOP, SKY_LOW, sun=(0.8, 0.2, 0.045))
    far = Layer(0.05, 0.4)
    mountains(far, 21, 0.44, 0.14, ATLAS, snow_line=0.36)
    cloud(far, 0.3, 0.17, 0.06)
    l2 = Layer(0.3)
    ground(l2, 0.47, (120, 160, 96), wav=0.012, seed=6)
    rnd = random.Random(2)
    for i in range(9):
        palm(l2, rnd.uniform(0, 1), 0.48, rnd.uniform(0.07, 0.1), seed=40 + i)
    l3 = Layer(0.6)
    pts = [(u / 60, 0.53 + 0.02 * math.sin(u / 60 * 5)) for u in range(61)]
    l3.poly([(0, 1)] + pts + [(1, 1)], LAWN)
    pts2 = [(u / 60, 0.58 + 0.025 * math.sin(u / 60 * 4 + 1.5)) for u in range(61)]
    l3.poly([(0, 1)] + pts2 + [(1, 1)], LAWN_L)
    l3.ellipse(0.66, 0.565, 0.13, 0.018, (150, 196, 110))  # green
    l3.ellipse(0.42, 0.60, 0.07, 0.012, SAND)               # bunker
    l3.line([(0.70, 0.565), (0.70, 0.49)], (240, 240, 240), 0.003)
    l3.poly([(0.70, 0.49), (0.76, 0.50), (0.70, 0.512)], (200, 60, 50))
    fg = Layer(1.0)
    fg.poly([(0, 1)] + [(u / 60, 0.78 + 0.03 * math.sin(u / 60 * 3)) for u in range(61)] + [(1, 1)], (90, 136, 72))
    palm(fg, 0.08, 1.0, 0.5, lean=0.05, seed=60)
    palm(fg, 0.92, 1.0, 0.56, lean=-0.05, seed=61)
    return bg, [far, l2, l3, fg]


def scene_ourika():
    bg = sky(SKY_BLUE_TOP, SKY_LOW)
    far = Layer(0.05, 0.3)
    mountains(far, 31, 0.40, 0.20, ATLAS, snow_line=0.29)
    l2 = Layer(0.3, 0.15)
    mountains(l2, 32, 0.50, 0.13, (160, 120, 96))
    l3 = Layer(0.55)
    ground(l3, 0.57, (196, 170, 128), seed=7)
    modern_villa(l3, 0.22, 0.60, 0.46, 0.12)
    pool(l3, 0.20, 0.605, 0.74, 0.635)
    for i, u in enumerate((0.1, 0.85, 0.93)):
        blob_tree(l3, u, 0.60, 0.035, OLIVE, seed=i)
    fg = Layer(1.0)
    ground(fg, 0.84, (170, 146, 108), seed=8)
    palm(fg, 0.04, 1.0, 0.44, lean=0.06, seed=70)
    blob_tree(fg, 0.92, 0.95, 0.09, OLIVE, seed=9)
    return bg, [far, l2, l3, fg]


def scene_hivernage():
    bg = sky(SKY_BLUE_TOP, SKY_LOW, sun=(0.18, 0.2, 0.045))
    far = Layer(0.05, 0.4)
    mountains(far, 41, 0.42, 0.08, ATLAS, snow_line=0.37)
    l2 = Layer(0.3, 0.1)
    rnd = random.Random(11)
    u = -0.02
    while u < 1.02:
        w = rnd.uniform(0.12, 0.2)
        box_house(l2, u, 0.55, w, rnd.uniform(0.08, 0.16), mix(PINK_L, SAND, rnd.random()),
                  win_col=GLASS, rnd=rnd, terrace=False)
        u += w + 0.01
    l3 = Layer(0.6)
    l3.rect(0, 0.55, 1, 1, (120, 110, 104))           # avenue
    l3.rect(0, 0.55, 1, 0.565, (200, 180, 160))
    for k in range(8):
        l3.rect(0.47, 0.60 + k * 0.05, 0.53, 0.625 + k * 0.05, (236, 232, 220))
    fg = Layer(1.0)
    for i, (u, h) in enumerate([(0.03, 0.62), (0.22, 0.5), (0.8, 0.5), (0.98, 0.62)]):
        palm(fg, u, 1.0, h, lean=(0.03 if u < 0.5 else -0.03), seed=80 + i)
    return bg, [far, l2, l3, fg]


def scene_gueliz():
    bg = sky(SKY_BLUE_TOP, SKY_LOW)
    far = Layer(0.05, 0.35)
    rnd = random.Random(12)
    u = -0.02
    while u < 1.02:
        w = rnd.uniform(0.08, 0.14)
        box_house(far, u, 0.50, w, rnd.uniform(0.10, 0.2), mix(PINK, SAND, 0.5), rnd=rnd, terrace=False)
        u += w + 0.005
    l2 = Layer(0.35)
    u = -0.05
    while u < 1.05:
        w = rnd.uniform(0.18, 0.26)
        h = rnd.uniform(0.14, 0.22)
        box_house(l2, u, 0.58, w, h, mix(PINK, PINK_L, rnd.random()), win_col=(80, 60, 60), rnd=rnd)
        for f in range(int(h / 0.035)):   # balcons
            y = 0.58 - h + 0.03 + f * 0.035
            l2.rect(u + w * 0.1, y, u + w * 0.9, y + 0.004, (240, 230, 220))
        u += w + 0.01
    l3 = Layer(0.65)
    l3.rect(0, 0.58, 1, 1, (150, 136, 126))
    l3.rect(0, 0.58, 1, 0.59, (220, 200, 180))
    fg = Layer(1.0)
    blob_tree(fg, 0.1, 0.9, 0.12, JACARANDA, seed=3)
    blob_tree(fg, 0.9, 0.86, 0.13, JACARANDA, seed=4)
    return bg, [far, l2, l3, fg]


def scene_medina():
    bg = sky(SKY_TOP, SKY_LOW, sun=(0.78, 0.26, 0.05))
    far = Layer(0.05, 0.35)
    mountains(far, 51, 0.40, 0.10, ATLAS, snow_line=0.335)
    l2 = Layer(0.3, 0.12)
    rnd = random.Random(13)
    u = -0.02
    while u < 1.02:
        w = rnd.uniform(0.05, 0.1)
        box_house(l2, u, 0.48, w, rnd.uniform(0.02, 0.06), mix(PINK, PINK_L, rnd.random()), rnd=rnd)
        u += w * 0.85
    minaret(l2, 0.34, 0.46, 0.20)
    l3 = Layer(0.6)
    u = -0.03
    while u < 1.03:
        w = rnd.uniform(0.12, 0.2)
        box_house(l3, u, 0.62, w, rnd.uniform(0.06, 0.12), mix(TERRA, PINK, rnd.random()), rnd=rnd)
        u += w * 0.9
    # arcs outrepassés au premier plan
    fg = Layer(1.0)
    fg.rect(0, 0.70, 1, 1, TERRA_D)
    for k, x in enumerate((0.17, 0.5, 0.83)):
        fg.rect(x - 0.13, 0.66, x + 0.13, 0.70, TERRA_D)
        fg.ellipse(x, 0.77, 0.105, 0.075, (60, 36, 30))
        fg.rect(x - 0.095, 0.77, x + 0.095, 1, (60, 36, 30))
    for k in range(12):  # zellige
        fg.rect(k / 12, 0.97, k / 12 + 0.04, 1, GREEN)
    return bg, [far, l2, l3, fg]


def scene_amizmiz():
    bg = sky(SKY_BLUE_TOP, SKY_LOW, sun=(0.7, 0.2, 0.045))
    far = Layer(0.05, 0.3)
    mountains(far, 61, 0.43, 0.17, ATLAS, snow_line=0.33)
    l2 = Layer(0.3)
    mountains(l2, 62, 0.53, 0.07, (190, 160, 110))
    l3 = Layer(0.6)
    ground(l3, 0.56, (206, 180, 130), wav=0.01, seed=9)
    rnd = random.Random(15)
    for i in range(5):
        box_house(l3, 0.18 + i * 0.13, 0.60, 0.1, 0.035, mix(SAND, WHITE, 0.5), win_col=GLASS, rnd=rnd)
    for i in range(14):
        blob_tree(l3, rnd.uniform(0, 1), 0.64 + rnd.uniform(0, 0.08), 0.025, OLIVE, seed=i)
    fg = Layer(1.0)
    ground(fg, 0.86, (180, 150, 104), seed=10)
    blob_tree(fg, 0.1, 0.96, 0.1, OLIVE, seed=21)
    blob_tree(fg, 0.9, 0.98, 0.11, OLIVE, seed=22)
    return bg, [far, l2, l3, fg]


def scene_theone():
    bg = sky(SKY_BLUE_TOP, SKY_LOW, sun=(0.2, 0.18, 0.045))
    far = Layer(0.05, 0.35)
    mountains(far, 71, 0.45, 0.09, ATLAS, snow_line=0.40)
    cloud(far, 0.75, 0.15, 0.05)
    l2 = Layer(0.35)
    ground(l2, 0.60, (190, 176, 150), seed=11)
    tower(l2, 0.36, 0.61, 0.28, 0.40, floors=16)
    tower(l2, 0.08, 0.61, 0.18, 0.22, floors=9, col=mix(WHITE, SAND, 0.4))
    tower(l2, 0.72, 0.61, 0.2, 0.27, floors=11, col=mix(WHITE, SAND, 0.2))
    l3 = Layer(0.6)
    pool(l3, 0.25, 0.62, 0.75, 0.66)
    fg = Layer(1.0)
    palm(fg, 0.06, 1.0, 0.55, lean=0.05, seed=90)
    palm(fg, 0.95, 1.0, 0.5, lean=-0.05, seed=91)
    return bg, [far, l2, l3, fg]


SCENES = {
    "hero-home.webm": scene_skyline,
    "palmeraie.jpg": scene_palmeraie,
    "golfs.jpg": scene_golfs,
    "ourika.jpg": scene_ourika,
    "hivernage.jpg": scene_hivernage,
    "gueliz.jpg": scene_gueliz,
    "medina.jpg": scene_medina,
    "amizmiz.jpg": scene_amizmiz,
    "theone": scene_theone,
}


class Scene:
    """Scène calquée prête à animer."""

    def __init__(self, name):
        bg, layers = SCENES[name]()
        self.name = name
        self.layers = [(0.0, bg)] + [(L.depth, L.final()) for L in layers]

    def frame(self, p, zoom=1.0, pan=1.0):
        """p ∈ [0,1] progression du plan ; zoom global (punch-in) ; parallaxe par profondeur."""
        out = None
        for depth, img in self.layers:
            z = zoom * (1.0 + 0.08 * p * (0.35 + 0.65 * depth))   # Ken Burns 1.00→1.08, plus fort devant
            shift = (p - 0.5) * 70 * depth * pan                  # glissement latéral différentiel
            vw, vh = W / z * (CW / W) / 1.08, H / z * (CW / W) / 1.08
            x0 = (CW - vw) / 2 + shift
            y0 = (CH - vh) / 2 + (p - 0.5) * 18 * depth
            s = vw / W
            t = img.transform((W, H), Image.AFFINE, (s, 0, x0, 0, s, y0), resample=Image.BICUBIC)
            out = t if out is None else Image.alpha_composite(out, t)
        return out.convert("RGB")

    def still(self):
        return self.frame(0.5)
