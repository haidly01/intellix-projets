# -*- coding: utf-8 -*-
"""WhatsApp outbound via Twilio Messages API + Content Templates (ContentSid)."""
import json
import logging

import requests

_logger = logging.getLogger(__name__)


class TwilioWhatsAppService:
    """POST /Accounts/{SID}/Messages.json avec ContentSid + ContentVariables."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _credentials(self):
        sid = (
            self._icp.get_param("doorway_callcenter_prospecting.twilio_account_sid")
            or self._icp.get_param("twilio.account_sid", "")
        ).strip()
        token = (
            self._icp.get_param("doorway_callcenter_prospecting.twilio_auth_token")
            or self._icp.get_param("twilio.auth_token", "")
        ).strip()
        return sid, token

    def _whatsapp_from(self):
        raw = (
            self._icp.get_param("doorway_callcenter_prospecting.twilio_whatsapp_from")
            or self._icp.get_param("twilio.whatsapp_from", "")
            or self._icp.get_param("doorway_messaging.twilio_whatsapp_from", "")
        ).strip()
        if not raw:
            return ""
        if raw.startswith("whatsapp:"):
            return raw
        if not raw.startswith("+"):
            raw = "+%s" % raw.lstrip("+")
        return "whatsapp:%s" % raw

    def _content_sid(self, sequence):
        key = "doorway_callcenter_prospecting.twilio_content_sid_%s" % sequence
        default_j0 = "HXb1a791a504786fa6732171b3fb3c31d4"
        if sequence == "j0":
            return (self._icp.get_param(key) or default_j0).strip()
        return (self._icp.get_param(key) or "").strip()

    def is_available(self):
        sid, token = self._credentials()
        return bool(sid and token and self._whatsapp_from())

    @staticmethod
    def _format_whatsapp_addr(phone_e164):
        phone = (phone_e164 or "").strip()
        if phone.startswith("whatsapp:"):
            return phone
        if not phone.startswith("+"):
            phone = "+%s" % phone.lstrip("+")
        return "whatsapp:%s" % phone

    def send_content_template(self, to_e164, content_sid, content_variables):
        """Envoie un template WhatsApp approuvé (équivalent curl ContentSid)."""
        sid, token = self._credentials()
        from_addr = self._whatsapp_from()
        if not sid or not token:
            return {"success": False, "error": "Twilio credentials manquants"}
        if not from_addr:
            return {"success": False, "error": "Numéro WhatsApp From non configuré"}
        if not content_sid:
            return {"success": False, "error": "ContentSid manquant"}
        to_addr = self._format_whatsapp_addr(to_e164)
        url = "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % sid
        payload = {
            "To": to_addr,
            "From": from_addr,
            "ContentSid": content_sid,
            "ContentVariables": json.dumps(content_variables or {}, ensure_ascii=False),
        }
        try:
            resp = requests.post(url, data=payload, auth=(sid, token), timeout=30)
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                message = data.get("message") or resp.text
                _logger.warning("Twilio WA template %s → %s : %s", content_sid, to_addr, message)
                return {"success": False, "error": message, "code": data.get("code")}
            return {
                "success": True,
                "sid": data.get("sid"),
                "status": data.get("status"),
            }
        except Exception as exc:  # noqa: BLE001
            _logger.error("Twilio WA template: %s", exc)
            return {"success": False, "error": str(exc)}

    def send_session_text(self, to_e164, body):
        """Réponse dans la fenêtre 24h (après réponse prospect) — Body libre."""
        sid, token = self._credentials()
        from_addr = self._whatsapp_from()
        if not sid or not token or not from_addr:
            return {"success": False, "error": "Twilio WhatsApp non configuré"}
        url = "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % sid
        payload = {
            "To": self._format_whatsapp_addr(to_e164),
            "From": from_addr,
            "Body": (body or "")[:4096],
        }
        try:
            resp = requests.post(url, data=payload, auth=(sid, token), timeout=30)
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                return {"success": False, "error": data.get("message") or resp.text}
            return {"success": True, "sid": data.get("sid")}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def send_sequence(self, to_e164, sequence, company_name, extra_vars=None):
        """
        sequence: j0 | j2 | j5 | qualified
        Variable {{1}} du template intellix = nom entreprise / contact.
        """
        content_sid = self._content_sid(sequence)
        if not content_sid and sequence != "j0":
            content_sid = self._content_sid("j0")
        variables = {"1": (company_name or "Bonjour")[:200]}
        if extra_vars:
            variables.update(extra_vars)
        return self.send_content_template(to_e164, content_sid, variables)
