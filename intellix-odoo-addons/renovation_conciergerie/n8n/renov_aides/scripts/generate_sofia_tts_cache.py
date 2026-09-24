#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère les MP3 Sofía (ElevenLabs) dans /var/www/sofia-tts/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

CONF = Path("/etc/odoo-server.conf")
OUT_DIR = Path("/var/www/sofia-tts")

REPLIQUES = {
    "sofia_hook": (
        "Buenos días. Le llamo por las ayudas de renovación energética "
        "de dos mil veintiséis. Es gratuito y solo un minutito."
    ),
    "sofia_question_propietario": (
        "¿Es usted propietario o propietaria de su vivienda?"
    ),
    "sofia_ouverture": (
        "Buenos días. Le llamo por las ayudas de renovación energética "
        "de dos mil veintiséis. Es gratuito y solo un minutito. "
        "¿Es usted propietario o propietaria de su vivienda?"
    ),
    "sofia_q1_clarif": (
        "Disculpe, no le he oído bien. ¿Es usted propietario de la vivienda? "
        "Puede decir sí, o ajá."
    ),
    "sofia_q2": (
        "Vale, anotado. Y en cuanto al tejado, ¿tiene una buhardilla "
        "o un desván sin aprovechar?"
    ),
    "sofia_q2_appt": (
        "De acuerdo. Aun así, un asesor puede comprobar otras ayudas disponibles "
        "para su vivienda. ¿Le interesaría que le contactáramos?"
    ),
    "sofia_q3": (
        "Muy bien. No todas las zonas de España se benefician igual de la ayuda, "
        "depende de dónde viva. ¿Podría facilitarme su código postal, por favor?"
    ),
    "sofia_q3_repeat": (
        "Solo necesito su código postal. Dígalo despacio, número por número."
    ),
    "sofia_q3_noknow": (
        "No se preocupe si no lo recuerda. Continuamos igualmente."
    ),
    "sofia_q4": (
        "Entendido. Una última pregunta: ¿qué sistema de calefacción utiliza actualmente, "
        "gas, gasóleo o electricidad?"
    ),
    "sofia_q4_non": (
        "Disculpe, no le he oído bien. ¿Utiliza gas, gasóleo o electricidad "
        "para la calefacción?"
    ),
    "sofia_q5": (
        "Perfecto. ¿Tiene acceso a esa buhardilla o desván?"
    ),
    "sofia_q5_non": (
        "De acuerdo. Un asesor puede evaluar otras soluciones técnicas con usted. "
        "¿Quiere que le contactemos?"
    ),
    "sofia_conclusion": (
        "Pues muy bien. En principio puede beneficiarse de estas nuevas ayudas "
        "de dos mil veintiséis. Un asesor especializado le contactará muy pronto "
        "para confirmar todos los detalles, sin ningún compromiso. "
        "¿Cuál sería el mejor momento — mañana por la mañana o por la tarde?"
    ),
    "sofia_exit_non_proprio": (
        "Entendido, muchas gracias por su tiempo. ¡Que tenga un buen día! ¡Hasta luego!"
    ),
    "sofia_exit_polite": (
        "Por supuesto, lo entiendo perfectamente. Muchas gracias. ¡Que tenga un buen día!"
    ),
    "sofia_exit_dnc": (
        "Por supuesto, le retiro de nuestra lista de contacto. Disculpe las molestias. ¡Hasta luego!"
    ),
    "sofia_exit_timeout": (
        "Disculpe, se me acaba el tiempo. ¿Le llamo en otro momento más conveniente?"
    ),
    "sofia_fallback": (
        "Entiendo. La idea es solo comprobar si puede acceder a una ayuda gratuita. "
        "¿Seguimos un momentito?"
    ),
    "sofia_collect_nom": (
        "Perfecto. ¿Puede confirmarme su nombre completo para que el asesor prepare su ficha?"
    ),
    "sofia_collect_tel": (
        "Perfecto. ¿El número en el que le llamamos ahora es el mejor para contactarle?"
    ),
    "sofia_fin_succes": (
        "Perfecto. Queda registrado. Un asesor especializado le contactará muy pronto. "
        "Muchas gracias por su tiempo. ¡Que tenga un buen día!"
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


def main() -> int:
    api_key = _read_conf("ELEVENLABS_API_KEY")
    voice_id = _read_conf("ELEVENLABS_VOICE_ID") or "IrS0oRyKeMCyPJVVpPyg"
    if not api_key:
        print("ELEVENLABS_API_KEY manquant", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in REPLIQUES.items():
        out = OUT_DIR / f"{name}.mp3"
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.42,
                    "similarity_boost": 0.88,
                    "style": 0.28,
                    "use_speaker_boost": True,
                    "speed": 0.86,
                },
            },
            timeout=120,
        )
        if r.status_code >= 400:
            print(f"ERROR {name}: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        out.write_bytes(r.content)
        print(f"✓ {name}.mp3 ({len(r.content)} bytes)")
    os.chmod(OUT_DIR, 0o755)
    for f in OUT_DIR.glob("*.mp3"):
        os.chmod(f, 0o644)
    print(f"Done → {OUT_DIR} ({len(REPLIQUES)} fichiers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
