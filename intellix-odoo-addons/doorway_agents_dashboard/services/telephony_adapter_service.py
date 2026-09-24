# -*- coding: utf-8 -*-
"""Couche d'abstraction téléphonie — Twilio / Telnyx / VICIdial (renov-aides v2)."""
import logging
import os

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TelephonyAdapterService:
    """Route les appels sortants selon TELEPHONY_PROVIDER (.env / odoo-server.conf)."""

    PROVIDERS = ("twilio", "telnyx", "vicidial")

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _env(self, key, icp_key=None, default=""):
        val = os.environ.get(key)
        if val:
            return val
        if icp_key:
            val = self._icp.get_param(icp_key)
            if val:
                return val
        return default

    def get_provider(self):
        return (
            self._env(
                "TELEPHONY_PROVIDER",
                "doorway_agents_dashboard.telephony_provider",
                "twilio",
            )
            or "twilio"
        ).lower()

    def n8n_webhook_base(self):
        return (
            self._env("N8N_WEBHOOK_URL", "doorway_agents_dashboard.n8n_webhook_url")
            or ""
        ).rstrip("/")

    def initiate_outbound_call(self, telephone, lead_id=None, nombre=None, campaign=None):
        """
        Déclenche un appel via n8n (recommandé) ou directement selon provider.
        Retourne dict {ok, provider, raw}.
        """
        phone = (telephone or "").strip()
        if not phone:
            raise UserError(_("Numéro de téléphone requis."))
        n8n = self.n8n_webhook_base()
        if n8n:
            try:
                response = requests.post(
                    "%s/renov/outbound" % n8n,
                    json={
                        "telephone": phone,
                        "lead_id": lead_id,
                        "nombre": nombre,
                        "campaign": campaign or "renov_es",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                return {
                    "ok": True,
                    "provider": self.get_provider(),
                    "mode": "n8n",
                    "raw": response.text,
                }
            except requests.RequestException as exc:
                _logger.warning("n8n outbound trigger: %s", exc)
                raise UserError(_("Échec déclenchement n8n : %s") % exc) from exc

        provider = self.get_provider()
        if provider == "vicidial":
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            result = VicidialService(self.env).call_out_number(
                phone,
                campaign=campaign or "renov_es",
                phone_code="34",
            )
            return {"ok": result.get("ok"), "provider": "vicidial", "raw": result}

        if provider == "telnyx":
            return self._telnyx_call(phone)

        return self._twilio_call(phone)

    def _twilio_call(self, telephone):
        from odoo.addons.doorway_agents_dashboard.services.twilio_service import (
            TwilioService,
        )

        twilio = TwilioService(self.env)
        if not twilio.is_available():
            raise UserError(_("Twilio non configuré."))
        cfg = twilio._config()
        base = self.n8n_webhook_base() or cfg["base_url"].rstrip("/")
        client = twilio._client()
        call = client.calls.create(
            to=telephone,
            from_=cfg["from"],
            url="%s/webhook/telephony/twilio/start" % base,
            record=True,
            machine_detection="DetectMessageEnd",
            timeout=30,
        )
        return {"ok": True, "provider": "twilio", "call_sid": call.sid}

    def _telnyx_call(self, telephone):
        api_key = self._env("TELNYX_API_KEY")
        if not api_key:
            raise UserError(_("TELNYX_API_KEY manquant."))
        base = self.n8n_webhook_base()
        response = requests.post(
            "https://api.telnyx.com/v2/calls",
            headers={
                "Authorization": "Bearer %s" % api_key,
                "Content-Type": "application/json",
            },
            json={
                "to": telephone,
                "from": self._env("TELNYX_PHONE_NUMBER"),
                "connection_id": self._env("TELNYX_CONNECTION_ID"),
                "webhook_url": "%s/telephony/telnyx/start" % base,
                "record_audio": True,
                "answering_machine_detection": "premium",
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise UserError(_("Telnyx appel échoué : %s") % response.text[:300])
        return {"ok": True, "provider": "telnyx", "raw": response.json()}
