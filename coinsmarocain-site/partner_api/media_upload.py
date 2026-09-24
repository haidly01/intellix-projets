"""Enregistre photos / vidéos envoyées par le commerçant."""
from __future__ import annotations

import os
import re
import secrets

MAX_VIDEO = 40 * 1024 * 1024
MAX_PHOTO = 8 * 1024 * 1024
MAX_PHOTOS = 6
MAX_BODY = 45 * 1024 * 1024

PHOTO_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
VIDEO_EXT = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


def parse_multipart(headers, body: bytes):
    ctype = headers.get("Content-Type") or ""
    match = re.search(r"boundary=([^;]+)", ctype, re.I)
    if not match:
        return {}, {}
    boundary = match.group(1).strip().strip('"')
    sep = b"--" + boundary.encode("utf-8", "replace")
    fields, files = {}, {}
    for chunk in body.split(sep):
        if not chunk or chunk.strip(b"-\r\n") == b"":
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        head, _, payload = chunk.partition(b"\r\n\r\n")
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        disp = ""
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                disp = line.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]+)"', disp)
        if not name_m:
            continue
        name = name_m.group(1)
        file_m = re.search(r'filename="([^"]*)"', disp)
        if file_m and file_m.group(1):
            files[name] = {"filename": file_m.group(1), "data": payload}
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields, files


def _ext(name: str, kind: str) -> str:
    raw = os.path.splitext(name or "")[1].lower()
    if kind == "video":
        return raw if raw in VIDEO_EXT else ".mp4"
    return raw if raw in PHOTO_EXT else ".jpg"


def save_file(upload_dir: str, url_prefix: str, account_id: str, kind: str, filename: str, data: bytes):
    if not data:
        return None, "empty"
    limit = MAX_VIDEO if kind == "video" else MAX_PHOTO
    if len(data) > limit:
        return None, "too_large"
    ext = _ext(filename, kind)
    allowed = VIDEO_EXT if kind == "video" else PHOTO_EXT
    if ext not in allowed:
        return None, "type"
    folder = os.path.join(upload_dir, account_id)
    os.makedirs(folder, exist_ok=True)
    stored = f"{kind}-{secrets.token_hex(6)}{ext}"
    path = os.path.join(folder, stored)
    with open(path, "wb") as fh:
        fh.write(data)
    url = f"{url_prefix.rstrip('/')}/{account_id}/{stored}"
    return url, None
