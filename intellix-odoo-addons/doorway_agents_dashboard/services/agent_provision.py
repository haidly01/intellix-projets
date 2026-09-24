# -*- coding: utf-8 -*-
"""Provisionnement ElevenLabs depuis le wizard de création."""
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

from .elevenlabs_client import BASE, ElevenLabsClient
from .elevenlabs_voicemail import inject_voicemail_detection

_logger = logging.getLogger(__name__)

LATENCY_CONV = {
    "low": {"turn_timeout": 5, "model_id": "eleven_turbo_v2_5"},
    "balanced": {"turn_timeout": 7, "model_id": "eleven_turbo_v2_5"},
    "quality": {"turn_timeout": 10, "model_id": "eleven_multilingual_v2"},
}


class AgentProvisionService:
    def __init__(self, env):
        self.env = env
        self.client = ElevenLabsClient(env)

    def _build_payload(self, profile):
        profile.ensure_one()
        voice_id = (profile.voice_id or profile.voice_clone_id or "").strip()
        if not voice_id:
            raise UserError(_("Voice ID manquant."))
        voice_id = self.client.ensure_voice_for_convai(
            voice_id,
            voice_name=profile.voice_name or profile.name,
        )
        mode = profile.latency_mode or "balanced"
        lat = LATENCY_CONV.get(mode, LATENCY_CONV["balanced"])
        speed = profile.voice_speed or 1.0
        stability = profile.voice_stability if profile.voice_stability is not None else 0.5
        first_messages = {
            "fr": "Bonjour, comment puis-je vous aider aujourd'hui ?",
            "en": "Hello, how can I help you today?",
            "es": "Hola, ¿cómo puedo ayudarle hoy?",
            "bilingual": "Bonjour / Hello, comment puis-je vous aider?",
        }
        lang = profile.language or "fr"
        el_lang = {"fr": "fr", "en": "en", "es": "es", "bilingual": "en"}.get(lang, "fr")
        first_message = profile.get_web_test_first_message()
        if not first_message:
            first_message = first_messages.get(lang, first_messages["fr"])
        payload = {
            "name": profile.name,
            "conversation_config": {
                "agent": {
                    "prompt": {"prompt": profile.system_prompt or ""},
                    "first_message": first_message,
                    "language": el_lang,
                },
                "tts": {
                    "voice_id": voice_id,
                    "model_id": lat["model_id"],
                    "voice_settings": {
                        "stability": stability,
                        "similarity_boost": 0.85,
                        "speed": speed,
                    },
                },
                "turn": {"turn_timeout": lat["turn_timeout"]},
            },
        }
        return inject_voicemail_detection(payload)

    def deploy_from_wizard(self, profile):
        profile.ensure_one()
        if not self.client.is_available():
            raise UserError(_("Clé API ElevenLabs non configurée."))
        payload = self._build_payload(profile)
        ext = (profile.external_agent_id or "").strip()
        if ext and ext.startswith("agent_"):
            response = requests.patch(
                "%s/convai/agents/%s" % (BASE, ext),
                headers=self.client.headers,
                json=payload,
                timeout=60,
            )
            if response.status_code < 400:
                return ext
        response = requests.post(
            "%s/convai/agents/create" % BASE,
            headers=self.client.headers,
            json=payload,
            timeout=60,
        )
        if response.status_code >= 400:
            raise UserError(
                self.client.parse_api_error(response)
                if hasattr(self.client, "parse_api_error")
                else _("Échec création agent ElevenLabs (%s): %s")
                % (response.status_code, response.text[:800])
            )
        body = response.json()
        agent_id = body.get("agent_id") or body.get("id") or ""
        if not agent_id:
            raise UserError(_("Réponse ElevenLabs sans agent_id."))
        self.client.sync_voicemail_detection_on_agent(agent_id)
        return agent_id
