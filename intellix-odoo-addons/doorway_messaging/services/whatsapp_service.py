# -*- coding: utf-8 -*-
"""WhatsApp via Twilio (REST API directe, sans SDK).

Supporte deux modes d'envoi :
  - corps libre (``body``) : uniquement valable dans la fenêtre de session 24h ;
  - template approuvé (``content_sid`` + ``content_variables``) : obligatoire
    pour les messages WhatsApp à l'initiative de l'entreprise (business-initiated).
"""
import json
import logging

import requests

_logger = logging.getLogger(__name__)

TWILIO_API = "https://api.twilio.com/2010-04-01"


class WhatsAppService:
    def __init__(self, env, from_number=None):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()
        self._from = from_number

    def _config(self):
        return {
            "sid": self._icp.get_param("doorway_messaging.twilio_account_sid")
            or self._icp.get_param("doorway_agents_dashboard.twilio_account_sid")
            or self._icp.get_param("twilio.account_sid", ""),
            "token": self._icp.get_param("doorway_messaging.twilio_auth_token")
            or self._icp.get_param("doorway_agents_dashboard.twilio_auth_token")
            or self._icp.get_param("twilio.auth_token", ""),
            "from": self._from
            or self._icp.get_param("doorway_messaging.twilio_whatsapp_from")
            or self._icp.get_param("twilio.whatsapp_from", ""),
            "messaging_service": self._icp.get_param(
                "doorway_messaging.twilio_whatsapp_messaging_service_sid"
            )
            or self._icp.get_param(
                "doorway_messaging.twilio_messaging_service_sid", ""
            ),
        }

    def is_available(self):
        c = self._config()
        return bool(c["sid"] and c["token"] and (c["from"] or c["messaging_service"]))

    def _fmt(self, number):
        n = (number or "").strip()
        if n.startswith("whatsapp:"):
            return n
        if not n.startswith("+"):
            n = "+%s" % n.lstrip("+")
        return "whatsapp:%s" % n

    def send_whatsapp(
        self,
        to_number,
        body=None,
        content_sid=None,
        content_variables=None,
        messaging_service_sid=None,
    ):
        c = self._config()
        if not self.is_available():
            return {"success": False, "error": "Twilio WhatsApp non configuré"}

        data = {"To": self._fmt(to_number)}

        msvc = messaging_service_sid or c["messaging_service"]
        if msvc:
            data["MessagingServiceSid"] = msvc
        else:
            frm = c["from"]
            data["From"] = (
                frm if frm.startswith("whatsapp:") else "whatsapp:%s" % frm
            )

        if content_sid:
            data["ContentSid"] = content_sid
            if content_variables:
                data["ContentVariables"] = (
                    content_variables
                    if isinstance(content_variables, str)
                    else json.dumps(content_variables, ensure_ascii=False)
                )
        else:
            data["Body"] = (body or "")[:4096]

        try:
            url = "%s/Accounts/%s/Messages.json" % (TWILIO_API, c["sid"])
            resp = requests.post(
                url, data=data, auth=(c["sid"], c["token"]), timeout=30
            )
            payload = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": payload.get("message") or resp.text,
                    "code": payload.get("code"),
                }
            return {"success": True, "sid": payload.get("sid", "")}
        except Exception as exc:  # noqa: BLE001
            _logger.error("Twilio WhatsApp: %s", exc)
            return {"success": False, "error": str(exc)}
