# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DoorwayClaudeController(http.Controller):
    @http.route("/doorway/claude/adapt_message", type="json", auth="user")
    def adapt_message(self, message="", context=""):
        """Reformule un message WhatsApp via Claude (fallback si clé absente)."""
        message = (message or "").strip()
        if not message:
            return {"adapted": "", "source": "empty"}

        from odoo.addons.doorway_messaging.services.claude_service import (
            ClaudeMessagingService,
        )

        svc = ClaudeMessagingService(request.env)
        key = svc._api_key()
        if not key:
            adapted = _fallback_adapt(message)
            return {"adapted": adapted, "source": "fallback", "warning": "no_api_key"}

        prompt = (
            "Reformule ce message WhatsApp pour qu'il soit plus engageant et "
            "professionnel, sans le dénaturer. Contexte : %s.\n"
            "Réponds uniquement avec le message reformulé, sans explication.\n\n"
            "Message original :\n%s"
        ) % (context or "whatsapp_lead_followup", message)

        adapted = svc._call(prompt, max_tokens=400)
        if adapted:
            return {"adapted": adapted, "source": "claude"}

        adapted = _fallback_adapt(message)
        return {"adapted": adapted, "source": "fallback", "warning": "claude_error"}


def _fallback_adapt(message):
    """Fallback léger sans API — ajoute une touche polie."""
    text = message.strip()
    if not text.lower().startswith("bonjour"):
        text = "Bonjour !\n\n" + text
    if not text.endswith(("!", ".", "?")):
        text += "."
    return text
