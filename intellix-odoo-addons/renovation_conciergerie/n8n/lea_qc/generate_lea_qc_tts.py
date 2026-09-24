#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère les MP3 des répliques de Léa (ElevenLabs) dans le bucket de clips.

Test A/B de scripts : variante A = répliques de production actuelles,
variante B = répliques alternatives (accroche + qualification reformulées).
La voix, le modèle et les voice_settings sont IDENTIQUES pour A et B afin que
seul le SCRIPT varie (coût/minute ≈ constant).

Usage :
    python3 generate_lea_qc_tts.py b      # uniquement la variante B (par défaut)
    python3 generate_lea_qc_tts.py a      # uniquement la variante A
    python3 generate_lea_qc_tts.py all    # A + B

Sortie : OUT_DIR/{key}.mp3  (doit correspondre à STORAGE_BUCKET_URL côté n8n).
NB : voice_settings alignées sur l'endpoint live /lea-tts (lea_qc_instrumented),
pour que les clips pré-rendus soient identiques à la synthèse live.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

CONF = Path("/etc/odoo-server.conf")
# Bucket des clips Léa — DOIT correspondre à STORAGE_BUCKET_URL (n8n) et à
# l'alias nginx /lea-qc-tts/ -> OUT_DIR.
OUT_DIR = Path(os.environ.get("LEA_TTS_DIR", "/var/www/lea-qc-tts"))

MODEL_ID = "eleven_multilingual_v2"
VOICE_SETTINGS = {"stability": 0.55, "similarity_boost": 0.82, "style": 0.35}

# Variante A — répliques de PRODUCTION ACTUELLE (contrôle, ne pas modifier).
REPLIQUES_A = {
    "lea_ouverture": (
        "Bonjour, ici Léa, l'assistante virtuelle automatisée de Soumission "
        "Entrepreneurs. On accompagne les propriétaires pour leurs projets de "
        "rénovation et aussi pour la vente de leur propriété. J'ai juste deux "
        "petites questions — ça prend moins d'une minute. Est-ce que vous êtes "
        "propriétaire de votre maison ?"
    ),
    "lea_exit_locataire": (
        "Je comprends, dans ce cas je ne peux pas vous aider pour l'instant. "
        "Bonne journée !"
    ),
    "lea_exit_locataire_info": (
        "Je comprends ! Dans ce cas, c'est votre propriétaire qui pourrait bénéficier "
        "des subventions et des rénovations. Si vous voulez, on peut lui envoyer "
        "l'information directement — ça pourrait améliorer votre logement. Bonne journée !"
    ),
    "lea_question_besoin": (
        "Parfait ! Est-ce que vous pensez plutôt à des travaux de rénovation, "
        "à vendre votre propriété, ou peut-être les deux ?"
    ),
    "lea_question_projet": (
        "Excellent ! Quels travaux envisagez-vous — cuisine, salle de bain, "
        "toiture, fenêtres, sous-sol, agrandissement ou autre chose ?"
    ),
    "lea_question_immo": (
        "Est-ce que vous envisagez de vendre votre propriété dans les prochains "
        "mois, disons dans les 12 à 24 prochains mois ?"
    ),
    "lea_capturer_dispo": (
        "Parfait ! Un conseiller de Soumission Entrepreneurs va vous rappeler pour "
        "discuter de votre projet. À quel moment préférez-vous qu'on vous contacte — "
        "le matin, l'après-midi ou le soir ?"
    ),
    "lea_redemand_dispo": (
        "À quel moment préférez-vous qu'on vous contacte — le matin, l'après-midi ou le soir ?"
    ),
    "lea_closing": (
        "Parfait ! Un conseiller vous rappelle au numéro qu'on a en dossier, "
        "comme convenu. Merci et bonne journée !"
    ),
    "lea_closing_matin": (
        "Parfait ! Un conseiller de Soumission Entrepreneurs vous rappellera le matin, "
        "au numéro qu'on a en dossier. Merci et bonne journée !"
    ),
    "lea_closing_apres_midi": (
        "Parfait ! Un conseiller de Soumission Entrepreneurs vous rappellera en après-midi, "
        "au numéro qu'on a en dossier. Merci et bonne journée !"
    ),
    "lea_closing_soir": (
        "Parfait ! Un conseiller de Soumission Entrepreneurs vous rappellera en soirée, "
        "au numéro qu'on a en dossier. Merci et bonne journée !"
    ),
    "lea_confirm_matin": "Donc le matin, c'est bien ça ?",
    "lea_confirm_apres_midi": "Donc l'après-midi, c'est bien ça ?",
    "lea_confirm_soir": "Donc le soir, c'est bien ça ?",
    "lea_sonder_futur": (
        "Je comprends, pas nécessairement là maintenant. Beaucoup de propriétaires "
        "commencent par une évaluation gratuite pour voir à quelles subventions ils "
        "ont droit, avant même de décider quoi faire. Est-ce qu'il y a quelque chose "
        "dans la maison qui vous préoccupe — l'isolation, le chauffage, les fenêtres ?"
    ),
    "lea_exit_futur": (
        "Pas de problème. Je note votre dossier et on pourra revenir vers vous "
        "quand vous serez prêt. Bonne journée !"
    ),
    "lea_exit_pas_interesse": (
        "Aucun problème ! Si vous changez d'idée, Soumission Entrepreneurs reste "
        "disponible. Bonne journée !"
    ),
    "lea_exit_pas_temps": (
        "Je comprends, vous êtes pris. On vous rappellera une autre fois. "
        "Bonne journée !"
    ),
    "lea_exit_pas_temps_v2": (
        "Je comprends, la vie est bien remplie ! Notre service ne vous demande "
        "presque aucun temps — on s'occupe de tout en arrière-plan. Est-ce qu'on "
        "pourrait fixer un moment plus tranquille, peut-être en soirée ou la fin "
        "de semaine ? Sinon je note et on vous rappelle une autre fois. Bonne journée !"
    ),
    "lea_objection_pas_interesse_soft": (
        "Je comprends, et je respecte ça ! Juste une question rapide — est-ce que "
        "c'est parce que vous n'avez pas de projet prévu, ou parce que vous ne "
        "connaissez pas encore notre service ? Beaucoup de propriétaires ne savent "
        "pas qu'on aide à accéder à des subventions jusqu'à dix mille dollars — "
        "sans frais et sans engagement."
    ),
    "lea_qui_etes_vous": (
        "Bonne question ! Je m'appelle Léa, de Soumission Entrepreneurs — une "
        "plateforme québécoise qui met en lien les propriétaires avec des "
        "entrepreneurs certifiés R-B-Q, et qui aide à accéder aux subventions "
        "gouvernementales. Notre service est cent pour cent gratuit et sans engagement."
    ),
    "lea_arnaque_sms_info": (
        "Je comprends votre méfiance — c'est normal avec tous les appels "
        "frauduleux. Soumission Entrepreneurs est vérifiable en ligne, on ne "
        "demande aucun paiement ni carte de crédit. Si vous préférez, je peux "
        "vous envoyer un texto avec notre site pour vérifier à votre rythme. "
        "Bonne journée !"
    ),
    "lea_rappeler_plus_tard": (
        "Pas de problème ! Pour vous rappeler au bon moment — est-ce que c'est "
        "plutôt dans un mois, trois mois, ou au printemps prochain ? Je note "
        "dans notre système. Bonne journée !"
    ),
    "lea_exit_dnc": (
        "C'est noté, on vous retire de notre liste. Bonne journée !"
    ),
    "lea_objection_entrepreneur": (
        "C'est parfait d'avoir un entrepreneur de confiance ! On est complémentaires — "
        "on vous aide à maximiser les subventions gouvernementales pour vos projets. "
        "Est-ce que votre entrepreneur vous a parlé de Rénoclimat ou LogisVert ? "
        "On peut quand même noter vos coordonnées pour rester en contact."
    ),
    "lea_fallback": (
        "Désolée, je n'ai pas bien entendu. Pouvez-vous répéter s'il vous "
        "plaît ?"
    ),
    "lea_exit_timeout": (
        "Je vois que vous êtes occupé — on vous rappellera une autre fois. "
        "Bonne journée !"
    ),
}

# Variante B — répliques ALTERNATIVES (test A/B). Doit rester synchronisée avec
# lea_qc_config.js (REPLIQUES_B) et data/lea_qc_scripted_lines.xml.
REPLIQUES_B = {
    "lea_ouverture_b": (
        "Bonjour, ici Léa, l'assistante virtuelle automatisée de Soumission "
        "Entrepreneurs. Bonne nouvelle pour les propriétaires : on aide à faire estimer "
        "gratuitement la valeur de votre maison. Ça prend trente secondes — "
        "êtes-vous bien propriétaire de votre maison ?"
    ),
    "lea_question_besoin_b": (
        "Super, merci ! Pour bien vous orienter : est-ce que ce qui vous "
        "intéresserait le plus en ce moment, ce serait de connaître la valeur "
        "de revente de votre maison, de réaliser des rénovations, ou un peu les "
        "deux ?"
    ),
    "lea_question_projet_b": (
        "Bon choix ! Concrètement, quel projet vous trotte dans la tête — la "
        "cuisine, la salle de bain, la toiture, les fenêtres, le sous-sol, un "
        "agrandissement, ou autre chose ?"
    ),
    "lea_question_immo_b": (
        "Parfait. Et juste pour savoir comment on peut vous aider : est-ce que "
        "vendre votre propriété, c'est quelque chose que vous envisagez d'ici un "
        "an ou deux, même sans être pressé ?"
    ),
    "lea_capturer_dispo_b": (
        "Excellent, c'est exactement notre spécialité ! Un conseiller va vous rappeler "
        "avec une évaluation gratuite pour votre projet. À quel moment préférez-vous "
        "qu'on vous contacte — le matin, l'après-midi ou le soir ?"
    ),
    "lea_redemand_dispo_b": (
        "À quel moment préférez-vous qu'on vous contacte — le matin, l'après-midi ou le soir ?"
    ),
    "lea_closing_b": (
        "Parfait, c'est noté ! Votre conseiller vous rappelle au numéro qu'on a au "
        "dossier, comme convenu. Merci beaucoup et excellente journée !"
    ),
    "lea_closing_matin_b": (
        "Parfait, c'est noté ! Votre conseiller vous rappellera le matin, au numéro "
        "qu'on a au dossier. Merci beaucoup et excellente journée !"
    ),
    "lea_closing_apres_midi_b": (
        "Parfait, c'est noté ! Votre conseiller vous rappellera en après-midi, au numéro "
        "qu'on a au dossier. Merci beaucoup et excellente journée !"
    ),
    "lea_closing_soir_b": (
        "Parfait, c'est noté ! Votre conseiller vous rappellera en soirée, au numéro "
        "qu'on a au dossier. Merci beaucoup et excellente journée !"
    ),
    "lea_sonder_futur_b": (
        "Aucun souci, rien d'urgent ! Juste pour le futur : y a-t-il un petit "
        "projet sur votre maison — rénovation ou même une vente éventuelle — que "
        "vous aimeriez garder dans un coin de votre tête pour plus tard ?"
    ),
    "lea_objection_entrepreneur_b": (
        "C'est une excellente chose d'avoir déjà quelqu'un ! On peut quand même "
        "vous offrir un deuxième avis gratuit, souvent ça aide à comparer. "
        "Est-ce que je peux noter vos coordonnées pour rester en contact ?"
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
    clip_keys = [a for a in sys.argv[2:] if not a.startswith("-")]

    if which == "clips":
        if not clip_keys:
            print("Usage: generate_lea_qc_tts.py clips lea_capturer_dispo ...", file=sys.stderr)
            return 1
        all_repliques = {**REPLIQUES_A, **REPLIQUES_B}
        repliques = {k: all_repliques[k] for k in clip_keys if k in all_repliques}
        missing = [k for k in clip_keys if k not in all_repliques]
        if missing:
            print(f"Clés inconnues: {missing}", file=sys.stderr)
            return 1
    elif which == "a":
        repliques = dict(REPLIQUES_A)
    elif which == "all":
        repliques = {**REPLIQUES_A, **REPLIQUES_B}
    else:
        repliques = dict(REPLIQUES_B)

    api_key = _read_conf("ELEVENLABS_API_KEY")
    voice_id = _read_conf("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        print("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID manquant", file=sys.stderr)
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
    print(f"Done -> {OUT_DIR} ({len(repliques)} fichiers, variante={which})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
