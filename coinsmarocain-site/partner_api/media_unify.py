"""Unifie photos / vidéos à la modération — même preset que cm_photo_batch."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PRESET = {
    "name": "coins-marocain-v1",
    "warmth": 0.07,
    "contrast": 1.07,
    "shadow_lift": 0.035,
    "saturation": 1.05,
    "wb_blend": 0.45,
    "jpeg_quality": 88,
}

REMOTE_VIDEO = ("youtu.be", "youtube.com", "vimeo.com")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_remote_video(url: str) -> bool:
    u = (url or "").lower()
    return any(h in u for h in REMOTE_VIDEO)


def is_local_upload(url: str, url_prefix: str) -> bool:
    if not url or url.startswith("data:"):
        return False
    prefix = (url_prefix or "").rstrip("/")
    return bool(prefix) and url.startswith(prefix + "/")


def url_to_path(upload_dir: str, url_prefix: str, url: str) -> str | None:
    prefix = (url_prefix or "").rstrip("/")
    if not url or not url.startswith(prefix + "/"):
        return None
    rel = url[len(prefix) + 1 :]
    if not rel or ".." in rel.split("/"):
        return None
    path = os.path.join(upload_dir, *rel.split("/"))
    return path if os.path.isfile(path) else None


def path_to_url(upload_dir: str, url_prefix: str, path: str) -> str:
    rel = os.path.relpath(path, upload_dir).replace(os.sep, "/")
    return f"{url_prefix.rstrip('/')}/{rel}"


def snapshot(acc: dict) -> dict:
    return {
        "id": acc.get("id") or "",
        "photos": list(acc.get("photos") or []),
        "photos_raw": list(acc.get("photos_raw") or []),
        "photos_carte": list(acc.get("photos_carte") or []),
        "video_url": acc.get("video_url") or "",
        "video_url_raw": acc.get("video_url_raw") or "",
        "video_poster": acc.get("video_poster") or "",
        "media_unified": bool(acc.get("media_unified")),
    }


def writeback(acc: dict, recap: dict) -> None:
    if recap.get("skipped") and recap.get("already"):
        acc["media_unified"] = True
        return
    acc["photos_raw"] = list(recap.get("photos_raw") or [])
    acc["photos"] = list(recap.get("photos") or [])
    acc["photos_carte"] = list(recap.get("photos_carte") or [])
    if "video_url_raw" in recap:
        acc["video_url_raw"] = recap.get("video_url_raw") or ""
    if "video_url" in recap:
        acc["video_url"] = recap.get("video_url") or ""
    acc["video_poster"] = recap.get("video_poster") or ""
    acc["media_unified"] = not recap.get("fatal")
    acc["media_unified_at"] = recap.get("at") or now_iso()
    acc["media_unify_recap"] = {
        "photos": recap.get("photos_done", 0),
        "videos": recap.get("videos_done", 0),
        "alerts": recap.get("alerts") or [],
        "preset": PRESET["name"],
    }


def mark_dirty(acc: dict) -> None:
    acc["media_unified"] = False


def listing_fields(acc: dict) -> dict:
    return {
        "photos_carte": acc.get("photos_carte") or [],
        "video_poster": acc.get("video_poster") or "",
        "media_unified": bool(acc.get("media_unified")),
    }


def _source_photos(snap: dict) -> list[str]:
    raw = [p for p in (snap.get("photos_raw") or []) if p]
    if raw:
        return raw
    return [p for p in (snap.get("photos") or []) if p and "/unified/" not in p]


def _source_video(snap: dict) -> str:
    raw = snap.get("video_url_raw") or ""
    if raw:
        return raw
    url = snap.get("video_url") or ""
    if url and "/unified/" not in url:
        return url
    return url


def process(snap: dict, upload_dir: str, url_prefix: str, force: bool = False) -> dict:
    photos_src = _source_photos(snap)
    video_src = _source_video(snap)
    local_photos = [u for u in photos_src if is_local_upload(u, url_prefix)]
    local_video = bool(video_src and is_local_upload(video_src, url_prefix) and not is_remote_video(video_src))
    has_work = bool(local_photos or local_video)

    if snap.get("media_unified") and not force and has_work:
        return {
            "ok": True,
            "skipped": True,
            "already": True,
            "photos": list(snap.get("photos") or []),
            "photos_raw": list(snap.get("photos_raw") or photos_src),
            "photos_carte": list(snap.get("photos_carte") or []),
            "video_url": snap.get("video_url") or "",
            "video_url_raw": snap.get("video_url_raw") or video_src,
            "video_poster": snap.get("video_poster") or "",
            "at": now_iso(),
        }

    if not has_work:
        return {
            "ok": True,
            "skipped": True,
            "photos": list(snap.get("photos") or photos_src),
            "photos_raw": photos_src,
            "photos_carte": list(snap.get("photos_carte") or []),
            "video_url": video_src or snap.get("video_url") or "",
            "video_url_raw": video_src if is_remote_video(video_src) else (snap.get("video_url_raw") or ""),
            "video_poster": snap.get("video_poster") or "",
            "photos_done": 0,
            "videos_done": 0,
            "alerts": [],
            "at": now_iso(),
        }

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return {"ok": False, "fatal": True, "error": "pillow_missing", "alerts": ["Pillow absent sur le serveur"]}

    dest = Path(upload_dir) / (snap.get("id") or "unknown") / "unified"
    dest.mkdir(parents=True, exist_ok=True)
    alerts = []
    fiche_urls = []
    carte_urls = []
    photos_done = 0

    for i, url in enumerate(local_photos, start=1):
        src = url_to_path(upload_dir, url_prefix, url)
        if not src:
            alerts.append(f"photo introuvable · {url}")
            continue
        try:
            fiche, carte = _export_photo(Path(src), dest, i)
        except Exception as exc:
            alerts.append(f"{os.path.basename(src)} · {exc}")
            continue
        fiche_urls.append(path_to_url(upload_dir, url_prefix, str(fiche)))
        carte_urls.append(path_to_url(upload_dir, url_prefix, str(carte)))
        photos_done += 1

    keep_remote = [u for u in photos_src if not is_local_upload(u, url_prefix)]
    photos_out = fiche_urls + keep_remote

    video_out = video_src
    video_raw = video_src if local_video else (snap.get("video_url_raw") or "")
    poster_url = snap.get("video_poster") or ""
    videos_done = 0
    if local_video:
        src = url_to_path(upload_dir, url_prefix, video_src)
        if not src:
            alerts.append(f"vidéo introuvable · {video_src}")
        else:
            vpath, ppath, verr = _export_video(Path(src), dest)
            if verr:
                alerts.append(verr)
            if vpath:
                video_out = path_to_url(upload_dir, url_prefix, str(vpath))
                videos_done = 1
            if ppath:
                poster_url = path_to_url(upload_dir, url_prefix, str(ppath))

    if not poster_url and carte_urls:
        poster_url = carte_urls[0]
    if not photos_out and poster_url:
        photos_out = [poster_url]

    if has_work and photos_done == 0 and videos_done == 0 and local_photos:
        return {
            "ok": False,
            "fatal": True,
            "error": "unify_failed",
            "alerts": alerts or ["aucun fichier traité"],
        }

    recap = {
        "ok": True,
        "photos": photos_out,
        "photos_raw": photos_src,
        "photos_carte": carte_urls,
        "video_url": video_out,
        "video_url_raw": video_raw or video_src,
        "video_poster": poster_url,
        "photos_done": photos_done,
        "videos_done": videos_done,
        "alerts": alerts,
        "preset": PRESET["name"],
        "at": now_iso(),
    }
    (dest / "recap.json").write_text(json.dumps(recap, ensure_ascii=False, indent=2), encoding="utf-8")
    return recap


def _export_photo(src: Path, dest: Path, index: int) -> tuple[Path, Path]:
    from PIL import Image, ImageOps

    from_correct = _apply_preset
    im = Image.open(src)
    im = ImageOps.exif_transpose(im) or im
    im = im.convert("RGB")
    corrected = from_correct(im, PRESET)
    quality = int(PRESET.get("jpeg_quality", 88))
    fiche = dest / f"fiche-{index:02d}.jpg"
    carte = dest / f"carte-{index:02d}.jpg"
    _save_usage(corrected, fiche, 1.0, 1600, quality)
    _save_usage(corrected, carte, 16 / 9, 1920, quality)
    return fiche, carte


def _save_usage(im, dest: Path, ratio: float, width: int, quality: int) -> None:
    crop = _center_crop(im, ratio)
    crop = _fit_width(crop, width)
    crop.save(dest, "JPEG", quality=quality, optimize=True)


def _export_video(src: Path, dest: Path) -> tuple[Path | None, Path | None, str]:
    ffmpeg = shutil.which("ffmpeg")
    poster_raw = dest / "_poster_raw.jpg"
    poster = dest / "poster.jpg"
    out = dest / "video.mp4"
    if not ffmpeg:
        return None, None, "ffmpeg absent — vidéo brute conservée"

    poster_path = None
    if _ffmpeg([
        ffmpeg, "-y", "-ss", "1", "-i", str(src),
        "-frames:v", "1", "-q:v", "2", str(poster_raw),
    ], timeout=40):
        try:
            from PIL import Image, ImageOps
            im = Image.open(poster_raw)
            im = ImageOps.exif_transpose(im) or im
            im = im.convert("RGB")
            corrected = _apply_preset(im, PRESET)
            _save_usage(corrected, poster, 16 / 9, 1920, int(PRESET.get("jpeg_quality", 88)))
            poster_path = poster
        except Exception as exc:
            if poster_raw.is_file():
                shutil.copy2(poster_raw, poster)
                poster_path = poster
            else:
                return None, None, f"poster · {exc}"

    vf = (
        "eq=contrast={c}:saturation={s}:gamma=1.02,"
        "colorbalance=rs=0.08:gs=0.02:bs=-0.05"
    ).format(c=PRESET["contrast"], s=PRESET["saturation"])
    ok = _ffmpeg([
        ffmpeg, "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k",
        str(out),
    ], timeout=180)
    if not ok:
        ok = _ffmpeg([
            ffmpeg, "-y", "-i", str(src),
            "-vf", f"eq=contrast={PRESET['contrast']}:saturation={PRESET['saturation']}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
            str(out),
        ], timeout=180)
    if not ok:
        return None, poster_path, "encodage vidéo échoué — fichier d’origine conservé"
    return out, poster_path, ""


def _ffmpeg(args: list[str], timeout: int) -> bool:
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _channel_means(im) -> tuple[float, float, float]:
    from PIL import ImageStat
    stat = ImageStat.Stat(im)
    return tuple(stat.mean[:3])  # type: ignore[return-value]


def _gray_world_wb(im, blend: float = 0.45):
    r, g, b = _channel_means(im)
    avg = (r + g + b) / 3.0 or 1.0
    factors = (avg / (r or 1.0), avg / (g or 1.0), avg / (b or 1.0))
    lut = []
    for ch in range(3):
        f = 1.0 + (factors[ch] - 1.0) * blend
        lut.extend([min(255, max(0, int(i * f))) for i in range(256)])
    return im.point(lut)


def _normalize_exposure(im):
    gray = im.convert("L")
    hist = gray.histogram()
    total = sum(hist) or 1
    acc = 0
    low = 0
    high = 255
    for i, n in enumerate(hist):
        acc += n
        if acc / total >= 0.02:
            low = i
            break
    acc = 0
    for i in range(255, -1, -1):
        acc += hist[i]
        if acc / total >= 0.02:
            high = i
            break
    if high <= low + 8:
        return im
    scale = 255.0 / (high - low)
    lut = [min(255, max(0, int((i - low) * scale))) for i in range(256)]
    return im.point(lut * 3)


def _apply_preset(im, preset: dict):
    from PIL import ImageEnhance, ImageOps
    im = ImageOps.autocontrast(im, cutoff=0.4)
    im = _normalize_exposure(im)
    im = _gray_world_wb(im, float(preset.get("wb_blend", 0.45)))
    warmth = float(preset.get("warmth", 0.07))
    if warmth:
        r_boost = 1.0 + warmth
        b_cut = 1.0 - warmth * 0.65
        lut = (
            [min(255, int(i * r_boost)) for i in range(256)]
            + [i for i in range(256)]
            + [min(255, max(0, int(i * b_cut))) for i in range(256)]
        )
        im = im.point(lut)
    lift = float(preset.get("shadow_lift", 0.035))
    if lift:
        lut = [min(255, int(i + (255 - i) * lift * (1 - i / 255))) for i in range(256)]
        im = im.point(lut * 3)
    contrast = float(preset.get("contrast", 1.07))
    if contrast != 1:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    sat = float(preset.get("saturation", 1.05))
    if sat != 1:
        im = ImageEnhance.Color(im).enhance(sat)
    return im


def _center_crop(im, ratio: float):
    """Garde le cadrage si déjà proche du ratio ; sinon coupe au centre (pas de zoom entropy)."""
    w, h = im.size
    if w < 8 or h < 8 or ratio <= 0:
        return im
    current = w / h
    if abs(current - ratio) < 0.08:
        return im
    if current > ratio:
        new_w = max(1, min(w, int(round(h * ratio))))
        x = (w - new_w) // 2
        return im.crop((x, 0, x + new_w, h))
    new_h = max(1, min(h, int(round(w / ratio))))
    y = (h - new_h) // 2
    return im.crop((0, y, w, y + new_h))


def _fit_width(im, width: int):
    from PIL import Image
    if im.width <= width:
        return im
    h = max(1, int(im.height * width / im.width))
    return im.resize((width, h), Image.LANCZOS)
