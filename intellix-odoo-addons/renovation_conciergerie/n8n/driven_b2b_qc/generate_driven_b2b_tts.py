#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère les MP3 des répliques d'Alex Driven B2B (ElevenLabs).

Usage:
    python3 generate_driven_b2b_tts.py

Sortie : OUT_DIR/{key}.mp3 + alex_ouverture.ulaw (8000 Hz mono) pour pre-cache Asterisk.
Voix : ELEVENLABS_VOICE_ID_ALEX (sinon ELEVENLABS_VOICE_ID).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import requests

CONF = Path("/etc/odoo-server.conf")
OUT_DIR = Path(os.environ.get("DRIVEN_TTS_DIR", "/var/www/driven-b2b-tts"))

MODEL_ID = "eleven_multilingual_v2"
VOICE_SETTINGS = {"stability": 0.55, "similarity_boost": 0.82, "style": 0.35}

REPLIQUES = {
    "alex_ouverture": (
        "Bonjour, c'est Alex de Agence Doorway. Je vous appelle parce que votre entreprise "
        "pourrait être admissible à du financement entre 10 000$ et 500 000$ en moins de 24 heures. "
        "Est-ce que c'est quelque chose qui vous intéresse ?"
    ),
    "alex_q1_anciennete": "Votre entreprise est en activité depuis combien de temps ?",
    "alex_q2_revenus": "Est-ce que votre entreprise génère au moins 100 000$ de revenus annuels ?",
    "alex_q3_compte": "Avez-vous un compte bancaire au nom de votre entreprise ?",
    "alex_closing_prequal": (
        "Parfait, vous êtes préqualifié. Je vous envoie tout de suite un lien sécurisé — "
        "ça prend 10 minutes, c'est gratuit et sans impact sur votre crédit. Prêt ?"
    ),
    "alex_no_compte": (
        "On peut quand même vous envoyer l'information, ça ne prend que 10 minutes à ouvrir."
    ),
    "alex_exit_anciennete": (
        "Malheureusement le minimum requis est 6 mois. Bonne continuation."
    ),
    "alex_exit_revenus": (
        "Je comprends. Pour l'instant nos critères exigent au moins 100 000$ de revenus annuels. "
        "Bonne continuation !"
    ),
    "alex_exit_pas_interesse": (
        "Aucun problème ! Si vous changez d'idée, Agence Doorway reste disponible. Bonne journée !"
    ),
    "alex_exit_dnc": "C'est noté, on vous retire de notre liste. Bonne journée !",
    "alex_fallback": (
        "Désolé, je n'ai pas bien entendu. Pouvez-vous répéter s'il vous plaît ?"
    ),
    "alex_exit_timeout": (
        "Je vois que vous êtes occupé — on pourra vous rappeler une autre fois. Bonne journée !"
    ),
}


def _read_conf(key: str) -> str:
    if not CONF.is_file():
        return ""
    for line in CONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _synthesize(api_key: str, voice_id: str, text: str) -> bytes:
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={"text": text, "model_id": MODEL_ID, "voice_settings": VOICE_SETTINGS},
        timeout=120,
    )
    r.raise_for_status()
    return r.content


def _mp3_to_ulaw(mp3_path: Path, ulaw_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-ar", "8000", "-ac", "1", "-f", "mulaw", str(ulaw_path),
        ],
        check=True,
        capture_output=True,
    )


def main() -> int:
    api_key = _read_conf("ELEVENLABS_API_KEY")
    voice_id = (
        os.environ.get("ELEVENLABS_VOICE_ID_ALEX")
        or _read_conf("ELEVENLABS_VOICE_ID_ALEX")
        or _read_conf("ELEVENLABS_VOICE_ID")
    )
    if not api_key or not voice_id:
        print("ELEVENLABS_API_KEY / voice_id manquant", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in REPLIQUES.items():
        try:
            audio = _synthesize(api_key, voice_id, text)
        except requests.RequestException as exc:
            print(f"ERROR {name}: {exc}", file=sys.stderr)
            return 1
        mp3 = OUT_DIR / f"{name}.mp3"
        mp3.write_bytes(audio)
        print(f"OK {name}.mp3 ({len(audio)} bytes)")

    opening_mp3 = OUT_DIR / "alex_ouverture.mp3"
    ulaw = OUT_DIR / "alex_ouverture.ulaw"
    gsm_cache = Path("/usr/share/asterisk/sounds/en/driven/alex_ouverture.gsm")
    greeting = Path("/tmp/greeting_ALEX.ulaw")
    if opening_mp3.is_file():
        _mp3_to_ulaw(opening_mp3, ulaw)
        greeting.write_bytes(ulaw.read_bytes())
        gsm_cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sox", str(opening_mp3), "-r", "8000", "-c", "1", str(gsm_cache.with_suffix(".wav"))],
            check=False,
            capture_output=True,
        )
        wav = gsm_cache.with_suffix(".wav")
        if wav.is_file():
            subprocess.run(["sox", str(wav), str(gsm_cache)], check=False, capture_output=True)
        print(f"OK alex_ouverture.ulaw + greeting -> {greeting}")

    os.chmod(OUT_DIR, 0o755)
    for f in OUT_DIR.glob("*"):
        os.chmod(f, 0o644)
    print(f"Done -> {OUT_DIR} ({len(REPLIQUES)} clips, voice={voice_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
