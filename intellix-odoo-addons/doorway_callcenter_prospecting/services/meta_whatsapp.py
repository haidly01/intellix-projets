# -*- coding: utf-8 -*-
"""WhatsApp outbound via Meta Cloud API (WABA Haidly / +1 555)."""
import logging

import requests

_logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"


class MetaWhatsAppService:
    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _config(self):
        return {
            "phone_id": (
                self._icp.get_param("doorway_social_ia.whatsapp_phone_number_id") or ""
            ).strip(),
            "token": (
                self._icp.get_param("doorway_social_ia.meta_system_user_token") or ""
            ).strip(),
        }

    def is_available(self):
        cfg = self._config()
        return bool(cfg["phone_id"] and cfg["token"])

    @staticmethod
    def _format_to(to_e164):
        return (
            (to_e164 or "")
            .replace("whatsapp:", "")
            .replace("+", "")
            .replace(" ", "")
            .strip()
        )

    def send_text(self, to_e164, body):
        cfg = self._config()
        if not self.is_available():
            return {"success": False, "error": "Meta WhatsApp non configuré"}
        to = self._format_to(to_e164)
        if not to:
            return {"success": False, "error": "Numéro destinataire vide"}
        url = "https://graph.facebook.com/%s/%s/messages" % (
            GRAPH_VERSION,
            cfg["phone_id"],
        )
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": "Bearer %s" % cfg["token"],
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": (body or "")[:4096]},
                },
                timeout=30,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400 or data.get("error"):
                err = data.get("error") or {}
                message = err.get("message") or resp.text
                _logger.warning("Meta WA → %s : %s", to, message)
                return {"success": False, "error": message}
            messages = data.get("messages") or []
            return {
                "success": True,
                "message_id": messages[0].get("id") if messages else None,
            }
        except Exception as exc:  # noqa: BLE001
            _logger.error("Meta WA send: %s", exc)
            return {"success": False, "error": str(exc)}
