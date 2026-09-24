#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pré-génère les greetings ElevenLabs Charlotte pour agents QC (ulaw 8kHz)."""
from __future__ import annotations

import os
import sys

import requests

VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "XB0fDUnXU5powFXDhCwa")

GREETINGS = {
    "SE": (
        "Bonjour ! Ici Émilie de SoumissionEntrepreneurs.com. "
        "On aide les propriétaires du Québec à trouver les meilleurs entrepreneurs "
        "pour leurs projets et à obtenir plusieurs soumissions gratuitement. "
        "J'ai juste deux petites questions pour vous, ça prend moins d'une minute. "
        "Est-ce que vous êtes propriétaire de votre maison ?"
    ),
    "MR": (
        "Bonjour ! Ici Sophie de MaisonRecherchee.com. "
        "On aide les propriétaires du Québec à vendre leur maison rapidement "
        "et au meilleur prix, grâce à notre réseau de courtiers partenaires. "
        "J'ai juste une question simple pour vous. "
        "Est-ce que vous envisagez de vendre votre propriété dans les prochains mois ?"
    ),
}


def main() -> int:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        conf = "/etc/odoo-server.conf"
        if os.path.isfile(conf):
            for line in open(conf, encoding="utf-8"):
                if line.strip().startswith("ELEVENLABS_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("ELEVENLABS_API_KEY manquant", file=sys.stderr)
        return 1

    for key, text in GREETINGS.items():
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.55,
                    "similarity_boost": 0.82,
                    "style": 0.35,
                    "use_speaker_boost": True,
                },
                "output_format": "ulaw_8000",
            },
            timeout=60,
        )
        response.raise_for_status()
        path = f"/tmp/greeting_{key}"
        with open(path + ".ulaw", "wb") as handle:
            handle.write(response.content)
        print(f"OK {path}.ulaw ({len(response.content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
