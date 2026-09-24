#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clone Instant Voice ElevenLabs depuis les samples espagnejeni."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

CONF = Path("/etc/odoo-server.conf")
SAMPLES = [
    Path("/var/www/sofia-tts/samples/jenni_clone_sample1.mp3"),
    Path("/var/www/sofia-tts/samples/jenni_clone_sample2.mp3"),
]
VOICE_NAME = "Sofia Jenni ES — renov-aides ref"


def _read_conf(key: str) -> str:
    if not CONF.is_file():
        return ""
    for line in CONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _set_conf(key: str, value: str) -> None:
    lines = CONF.read_text(encoding="utf-8").splitlines()
    out = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    CONF.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    api_key = _read_conf("ELEVENLABS_API_KEY")
    if not api_key:
        print("ELEVENLABS_API_KEY manquant", file=sys.stderr)
        return 1
    for p in SAMPLES:
        if not p.is_file():
            print(f"Sample manquant: {p}", file=sys.stderr)
            return 1

    files = []
    handles = []
    try:
        for sample in SAMPLES:
            fh = sample.open("rb")
            handles.append(fh)
            files.append(("files", (sample.name, fh, "audio/mpeg")))
        resp = requests.post(
            "https://api.elevenlabs.io/v1/voices/add",
            headers={"xi-api-key": api_key},
            data={
                "name": VOICE_NAME,
                "description": "Clone depuis espagnejeni.mp3 — appel référence ES renov-aides",
            },
            files=files,
            timeout=180,
        )
    finally:
        for fh in handles:
            fh.close()

    if resp.status_code >= 400:
        print(f"ElevenLabs clone error {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 1

    payload = resp.json()
    voice_id = payload.get("voice_id") or ""
    if not voice_id:
        print(f"Pas de voice_id: {payload}", file=sys.stderr)
        return 1

    _set_conf("ELEVENLABS_VOICE_ID", voice_id)
    print(json.dumps({"voice_id": voice_id, "name": VOICE_NAME}, indent=2))
    print(f"ELEVENLABS_VOICE_ID mis à jour dans {CONF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
