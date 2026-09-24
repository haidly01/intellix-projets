#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste la transcription Deepgram (espagnol) sur un fichier audio local ou une URL.

Exemples :
  python3 test_deepgram_audio.py /chemin/vers/bon_appel.mp3
  python3 test_deepgram_audio.py "https://api.twilio.com/2010-04-01/Accounts/.../Recordings/RE....mp3"
  python3 test_deepgram_audio.py --etape ouverture /chemin/reponse_propietario.wav
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

CONF = Path("/etc/odoo-server.conf")
SAMPLES_DIR = Path("/var/www/sofia-tts/samples")


def _read_conf(key: str) -> str:
    if not CONF.is_file():
        return ""
    for line in CONF.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _classify_es(etape: str, transcript: str) -> str:
    t = (transcript or "").lower()
    t = re.sub(r"[^\w\sáéíóúñ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return "silence"
    owner = bool(
        re.search(r"\b(propietari[oa]|titular|dueno|dueño)\b", t)
        or re.search(r"\bsoy\b", t)
    )
    if etape in ("ouverture", "Q1_clarif"):
        if owner or re.search(r"\b(si|sí|aja|ajá|claro|vale|correcto)\b", t):
            return "oui"
        if re.search(r"\b(inquilino|arrendatari|no soy)\b", t) or t in ("no", "nop"):
            return "non"
    return "incertain"


def _twilio_auth() -> tuple[str, str]:
    sid = _read_conf("TWILIO_ACCOUNT_SID")
    token = _read_conf("TWILIO_AUTH_TOKEN")
    return sid, token


def transcribe(source: str, api_key: str) -> dict:
    url = (
        "https://api.deepgram.com/v1/listen"
        "?language=es&model=nova-2&smart_format=true"
    )
    headers = {"Authorization": f"Token {api_key}"}

    if source.startswith("http://") or source.startswith("https://"):
        sid, token = _twilio_auth()
        if "api.twilio.com" in source and sid and token:
            audio = requests.get(source, auth=(sid, token), timeout=120)
            audio.raise_for_status()
            resp = requests.post(
                url,
                headers={**headers, "Content-Type": "audio/mpeg"},
                data=audio.content,
                timeout=120,
            )
        else:
            resp = requests.post(
                url,
                headers={**headers, "Content-Type": "application/json"},
                json={"url": source},
                timeout=120,
            )
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(path)
        with path.open("rb") as f:
            resp = requests.post(
                url,
                headers={**headers, "Content-Type": "audio/mpeg"},
                data=f.read(),
                timeout=120,
            )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Deepgram Sofía (ES)")
    parser.add_argument("audio", help="Chemin fichier local (.mp3/.wav) ou URL HTTPS")
    parser.add_argument(
        "--etape",
        default="ouverture",
        help="Étape du script pour test classification (ouverture, Q1_clarif, Q2…)",
    )
    parser.add_argument(
        "--copy-to-samples",
        action="store_true",
        help="Copie le fichier local vers /var/www/sofia-tts/samples/",
    )
    args = parser.parse_args()

    api_key = _read_conf("DEEPGRAM_API_KEY") or __import__("os").environ.get("DEEPGRAM_API_KEY", "")
    if not api_key:
        print("DEEPGRAM_API_KEY introuvable (/etc/odoo-server.conf)", file=sys.stderr)
        return 1

    audio_path = args.audio
    if args.copy_to_samples and not audio_path.startswith("http"):
        src = Path(audio_path)
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        dest = SAMPLES_DIR / src.name
        dest.write_bytes(src.read_bytes())
        print(f"Copié → {dest}")
        print(f"URL publique → https://intellixcrm.com/sofia-tts/samples/{src.name}")
        audio_path = str(dest)

    data = transcribe(audio_path, api_key)
    alt = (
        data.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
    )
    transcript = (alt.get("transcript") or "").strip()
    confidence = alt.get("confidence")

    print("--- Transcription Deepgram (ES) ---")
    print(transcript or "(vide)")
    if confidence is not None:
        print(f"Confiance : {confidence:.2%}")
    print(f"Intent rapide [{args.etape}] : {_classify_es(args.etape, transcript)}")
    print("--- JSON brut (extrait) ---")
    print(json.dumps({"transcript": transcript, "confidence": confidence}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
