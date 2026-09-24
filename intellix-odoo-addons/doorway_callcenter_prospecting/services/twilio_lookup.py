# -*- coding: utf-8 -*-
"""Twilio Lookup v2 — validation mobile / WhatsApp capable."""
import logging
from base64 import b64encode

import requests

_logger = logging.getLogger(__name__)


class TwilioLookupService:
    def __init__(self, env):
        self.env = env
        icp = env["ir.config_parameter"].sudo()
        self.sid = (
            icp.get_param("doorway_messaging.twilio_account_sid")
            or icp.get_param("doorway_agents_dashboard.twilio_account_sid")
            or icp.get_param("twilio.account_sid", "")
        )
        self.token = (
            icp.get_param("doorway_messaging.twilio_auth_token")
            or icp.get_param("doorway_agents_dashboard.twilio_auth_token")
            or icp.get_param("twilio.auth_token", "")
        )

    def is_available(self):
        return bool(self.sid and self.token)

    def lookup_phone(self, phone_e164):
        phone = (phone_e164 or "").strip()
        if not phone.startswith("+"):
            phone = "+%s" % phone.lstrip("+")
        if not self.is_available():
            return {
                "phone": phone,
                "valid": False,
                "error": "Twilio non configuré",
                "whatsapp_capable": False,
            }
        url = (
            "https://lookups.twilio.com/v2/PhoneNumbers/%s"
            "?Fields=line_type_intelligence" % requests.utils.quote(phone)
        )
        auth = b64encode(("%s:%s" % (self.sid, self.token)).encode()).decode()
        try:
            resp = requests.get(
                url,
                headers={"Authorization": "Basic %s" % auth},
                timeout=20,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                return {
                    "phone": phone,
                    "valid": False,
                    "error": data.get("message") or resp.text,
                    "whatsapp_capable": False,
                }
            lti = data.get("line_type_intelligence") or {}
            line_type = (lti.get("type") or "").lower()
            valid = bool(data.get("valid"))
            whatsapp_capable = valid and line_type in ("mobile", "voip", "nonfixedvoip")
            return {
                "phone": phone,
                "valid": valid,
                "line_type": line_type,
                "carrier": lti.get("carrier_name"),
                "whatsapp_capable": whatsapp_capable,
            }
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Twilio lookup %s: %s", phone, exc)
            return {
                "phone": phone,
                "valid": False,
                "error": str(exc),
                "whatsapp_capable": False,
            }
