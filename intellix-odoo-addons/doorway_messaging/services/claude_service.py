# -*- coding: utf-8 -*-
"""Claude API — adaptation contenu multicanal."""
import logging

import requests

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
SONNET_MODEL = "claude-sonnet-4-20250514"

CANAL_CONTRAINTES = {
    "sms": {
        "max_chars": 160,
        "ton": "ultra-concis, direct, pas d'emoji",
        "format": "texte brut uniquement",
    },
    "whatsapp": {
        "max_chars": 1000,
        "ton": "chaleureux, conversationnel, emojis modérés",
        "format": "texte avec *gras* et _italique_ WhatsApp, 1-2 emojis max",
    },
    "linkedin": {
        "max_chars": 3000,
        "ton": "professionnel, expert, inspirant",
        "format": "paragraphes aérés, 3-5 hashtags pertinents en fin de post",
    },
    "gmb": {
        "max_chars": 1500,
        "ton": "local, accessible, orienté action",
        "format": "texte simple, 1 appel à l'action clair, pas de hashtags",
    },
    "email": {
        "max_chars": 5000,
        "ton": "professionnel adapté à la marque",
        "format": "HTML structuré avec titre H2, paragraphes, 1 bouton CTA",
    },
}


class ClaudeMessagingService:
    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _api_key(self):
        return (
            self._icp.get_param("doorway_messaging.claude_api_key")
            or self._icp.get_param("doorway_agents_dashboard.anthropic_api_key")
            or self._icp.get_param("doorway_agents_ia.anthropic_api_key")
            or ""
        )

    def _headers(self):
        return {
            "x-api-key": self._api_key(),
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _call(self, prompt, max_tokens=1000):
        key = self._api_key()
        if not key:
            return ""
        try:
            response = requests.post(
                CLAUDE_API_URL,
                headers=self._headers(),
                json={
                    "model": SONNET_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45,
            )
            if response.status_code != 200:
                _logger.warning("Claude HTTP %s", response.status_code)
                return ""
            parts = response.json().get("content") or []
            return "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001
            _logger.error("Claude API: %s", exc)
            return ""

    def adapter_contenu_multicanal(self, corps_master, canaux_actifs, marque="IntelliX", langue="fr"):
        adaptations = {}
        for canal in canaux_actifs:
            contraintes = CANAL_CONTRAINTES.get(canal, {})
            prompt = (
                "Tu es un expert en marketing digital multicanal.\n\n"
                "Adapte ce message pour le canal %s de la marque %s.\n\n"
                "MESSAGE ORIGINAL :\n%s\n\n"
                "CONTRAINTES STRICTES %s :\n"
                "- Maximum %s caractères\n"
                "- Ton : %s\n"
                "- Format : %s\n"
                "- Langue : %s\n\n"
                "Retourne UNIQUEMENT le texte adapté, sans explication ni guillemets."
            ) % (
                canal.upper(),
                marque,
                corps_master,
                canal.upper(),
                contraintes.get("max_chars", 500),
                contraintes.get("ton", "professionnel"),
                contraintes.get("format", "texte"),
                langue,
            )
            texte = self._call(prompt)
            adaptations[canal] = texte or corps_master
            _logger.info("Claude adapté %s: %d chars", canal, len(adaptations[canal]))
        return adaptations

    def generer_sujet_email(self, corps, marque="IntelliX"):
        prompt = (
            "Génère un sujet d'email accrocheur en français (max 60 caractères)\n"
            "pour ce message de la marque %s :\n\n%s\n\n"
            "Retourne UNIQUEMENT le sujet, sans guillemets."
        ) % (marque, (corps or "")[:500])
        return self._call(prompt, max_tokens=80) or "Message important"
