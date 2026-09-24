#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère les MP3 des répliques de Léa FRANCE (Ma Réno Facile) via ElevenLabs.

Clone fidèle de lea_qc/generate_lea_qc_tts.py. Différences France :
  - VOIX native fr-FR (Marine — parisien, conversationnel) : voice_id
    6FXyooAOTqUK8m2HWm32 (surchargeable via ELEVENLABS_VOICE_ID_FR).
  - Sortie : /var/www/lea-fr-tts/{key}.mp3 (bucket FR dédié, alias nginx /lea-fr-tts/).
Les voice_settings/modèle restent IDENTIQUES à QC pour cohérence A/B (seul le
SCRIPT et la VOIX changent).

Usage :
    python3 generate_lea_fr_tts.py b      # variante B (défaut)
    python3 generate_lea_fr_tts.py a      # variante A
    python3 generate_lea_fr_tts.py all    # A + B
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

CONF = Path("/etc/odoo-server.conf")
OUT_DIR = Path(os.environ.get("LEA_FR_TTS_DIR", "/var/www/lea-fr-tts"))

MODEL_ID = "eleven_multilingual_v2"
VOICE_SETTINGS = {"stability": 0.55, "similarity_boost": 0.82, "style": 0.35}
# Voix native fr-FR « Marine — Premium Conversational AI » (accent parisien).
DEFAULT_FR_VOICE_ID = "6FXyooAOTqUK8m2HWm32"

# Variante A — PRODUCTION France (Ma Réno Facile, français de France, rénovation).
REPLIQUES_A = {
    "lea_ouverture": (
        "Bonjour, ici Léa, l'assistante virtuelle automatisée de Ma Réno Facile. "
        "Nous accompagnons les propriétaires dans leurs projets de rénovation de "
        "leur logement. J'ai juste deux petites questions, ça prend moins d'une "
        "minute. Êtes-vous bien propriétaire de votre logement ?"
    ),
    "lea_exit_locataire": (
        "Je comprends, dans ce cas nous ne pourrons pas vous aider pour le moment. "
        "Je vous souhaite une bonne journée !"
    ),
    "lea_question_besoin": (
        "Parfait ! Pensez-vous plutôt à des travaux de rénovation — par exemple "
        "l'isolation, le chauffage ou la rénovation d'une pièce —, à faire estimer "
        "la valeur de votre bien, ou peut-être les deux ?"
    ),
    "lea_question_projet": (
        "Très bien ! Quels travaux envisagez-vous — cuisine, salle de bains, "
        "isolation, chauffage, fenêtres, toiture, ou autre chose ?"
    ),
    "lea_question_immo": (
        "Souhaitez-vous faire estimer la valeur de votre bien, par exemple après "
        "vos travaux, dans les prochains mois ?"
    ),
    "lea_capturer_dispo": (
        "Super, c'est exactement pour cela que nous sommes là ! Un conseiller Ma "
        "Réno Facile vous rappellera pour étudier votre projet en détail. Quel est "
        "le meilleur moment pour vous — plutôt le matin, l'après-midi ou en soirée ?"
    ),
    "lea_closing": (
        "Parfait ! Je confirme, nous vous rappellerons au numéro que nous avons "
        "dans votre dossier. Merci pour votre temps et excellente journée !"
    ),
    "lea_sonder_futur": (
        "Je comprends, ce n'est pas forcément pour tout de suite. Avez-vous un "
        "projet de rénovation que vous aimeriez réaliser dans les prochains mois ?"
    ),
    "lea_exit_futur": (
        "Pas de souci. Je note votre dossier et nous reviendrons vers vous quand "
        "vous serez prêt. Bonne journée !"
    ),
    "lea_exit_pas_interesse": (
        "Très bien, aucun problème ! Si vous changez d'avis, Ma Réno Facile reste "
        "à votre disposition. Bonne journée !"
    ),
    "lea_exit_dnc": (
        "C'est noté, nous vous retirons de notre liste d'appel. Bonne journée !"
    ),
    "lea_objection_entrepreneur": (
        "C'est une très bonne chose ! Nous pouvons tout de même vous proposer un "
        "deuxième avis gratuit pour comparer. Puis-je noter vos coordonnées pour "
        "que nous restions en contact ?"
    ),
    "lea_fallback": (
        "Désolée, je n'ai pas bien entendu. Pouvez-vous répéter, s'il vous plaît ?"
    ),
    "lea_exit_timeout": (
        "Je vois que vous êtes occupé, nous vous rappellerons à un autre moment. "
        "Bonne journée !"
    ),
}

# Variante B — alternative (diagnostic gratuit + qualification reformulée).
REPLIQUES_B = {
    "lea_ouverture_b": (
        "Bonjour, ici Léa, l'assistante virtuelle automatisée de Ma Réno Facile. "
        "Bonne nouvelle pour les propriétaires : nous aidons à organiser vos "
        "travaux de rénovation avec un diagnostic gratuit. Ça prend trente "
        "secondes — êtes-vous bien propriétaire de votre logement ?"
    ),
    "lea_question_besoin_b": (
        "Super, merci ! Pour bien vous orienter : ce qui vous intéresserait le "
        "plus en ce moment, ce serait plutôt des travaux de rénovation, connaître "
        "la valeur de votre bien, ou un peu les deux ?"
    ),
    "lea_question_projet_b": (
        "Très bon choix ! Concrètement, quel projet avez-vous en tête — la "
        "cuisine, la salle de bains, l'isolation, le chauffage, les fenêtres, la "
        "toiture, ou autre chose ?"
    ),
    "lea_question_immo_b": (
        "Parfait. Et juste pour savoir comment vous aider au mieux : faire estimer "
        "la valeur de votre bien, c'est quelque chose que vous envisagez d'ici un "
        "an ou deux, même sans être pressé ?"
    ),
    "lea_capturer_dispo_b": (
        "Excellent, c'est tout à fait notre spécialité ! Un conseiller Ma Réno "
        "Facile vous rappellera avec un diagnostic gratuit et des idées concrètes "
        "pour votre projet. Pour qu'il tombe au bon moment, préférez-vous plutôt "
        "le matin, l'après-midi ou la soirée ?"
    ),
    "lea_closing_b": (
        "Parfait, c'est noté ! Votre conseiller Ma Réno Facile vous rappellera au "
        "numéro de votre dossier, au moment que vous avez choisi. Merci beaucoup "
        "et très belle journée !"
    ),
    "lea_sonder_futur_b": (
        "Aucun souci, rien d'urgent ! Juste pour l'avenir : y a-t-il un projet de "
        "rénovation sur votre logement que vous aimeriez garder en tête pour plus "
        "tard ?"
    ),
    "lea_objection_entrepreneur_b": (
        "C'est une excellente chose d'avoir déjà quelqu'un ! Nous pouvons tout de "
        "même vous offrir un deuxième avis gratuit, souvent ça aide à comparer. "
        "Puis-je noter vos coordonnées pour rester en contact ?"
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


def main() -> int:
    which = (sys.argv[1].lower() if len(sys.argv) > 1 else "b")
    if which == "a":
        repliques = dict(REPLIQUES_A)
    elif which == "all":
        repliques = {**REPLIQUES_A, **REPLIQUES_B}
    else:
        repliques = dict(REPLIQUES_B)

    api_key = _read_conf("ELEVENLABS_API_KEY")
    # Voix France dédiée (ne PAS réutiliser la voix QC fr-CA).
    voice_id = (
        os.environ.get("ELEVENLABS_VOICE_ID_FR")
        or _read_conf("ELEVENLABS_VOICE_ID_FR")
        or DEFAULT_FR_VOICE_ID
    )
    if not api_key or not voice_id:
        print("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID_FR manquant", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in repliques.items():
        try:
            audio = _synthesize(api_key, voice_id, text)
        except requests.RequestException as exc:
            print(f"ERROR {name}: {exc}", file=sys.stderr)
            return 1
        (OUT_DIR / f"{name}.mp3").write_bytes(audio)
        print(f"OK {name}.mp3 ({len(audio)} bytes)")

    os.chmod(OUT_DIR, 0o755)
    for f in OUT_DIR.glob("*.mp3"):
        os.chmod(f, 0o644)
    print(f"Done -> {OUT_DIR} ({len(repliques)} fichiers, variante={which}, voice={voice_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
