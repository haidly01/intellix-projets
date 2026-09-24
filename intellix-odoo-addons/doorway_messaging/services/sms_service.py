# -*- coding: utf-8 -*-
"""SMS via Twilio (REST API directe, sans SDK).

Supporte l'envoi par corps libre (``body``) ou par template Twilio Content
approuvé (``content_sid`` + ``content_variables``).
"""
import json
import logging

import requests

_logger = logging.getLogger(__name__)

TWILIO_API = "https://api.twilio.com/2010-04-01"


class SmsService:
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
            or self._icp.get_param("doorway_messaging.twilio_sms_from")
            or self._icp.get_param("doorway_agents_dashboard.twilio_phone_number")
            or self._icp.get_param("twilio.from_number", ""),
            "messaging_service": self._icp.get_param(
                "doorway_messaging.twilio_messaging_service_sid", ""
            ),
        }

    def is_available(self):
        c = self._config()
        return bool(c["sid"] and c["token"] and (c["from"] or c["messaging_service"]))

    @staticmethod
    def _fmt(number):
        n = (number or "").strip()
        return n if n.startswith("+") else "+%s" % n.lstrip("+")

    def send_sms(
        self,
        to_number,
        body=None,
        content_sid=None,
        content_variables=None,
        messaging_service_sid=None,
    ):
        c = self._config()
        if not self.is_available():
            return {"success": False, "error": "Twilio SMS non configuré"}

        data = {"To": self._fmt(to_number)}

        msvc = messaging_service_sid or c["messaging_service"]
        if msvc:
            data["MessagingServiceSid"] = msvc
        else:
            data["From"] = c["from"]

        if content_sid:
            data["ContentSid"] = content_sid
            if content_variables:
                data["ContentVariables"] = (
                    content_variables
                    if isinstance(content_variables, str)
                    else json.dumps(content_variables, ensure_ascii=False)
                )
        else:
            data["Body"] = (body or "")[:1600]

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
            _logger.error("Twilio SMS: %s", exc)
            return {"success": False, "error": str(exc)}
