# -*- coding: utf-8 -*-
"""ElevenLabs Conversational AI — mode dégradé sans clé API."""
import json
import logging

import requests

_logger = logging.getLogger(__name__)


class ElevenlabsService:
    """Intégration ElevenLabs (appels conversationnels)."""

    BASE = "https://api.elevenlabs.io/v1"

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _api_key(self):
        return (
            self._icp.get_param("doorway_agents_dashboard.elevenlabs_api_key")
            or self._icp.get_param("doorway_agents_ia.elevenlabs_api_key", "")
        )

    def _guard_and_debit_elevenlabs(self, minutes=1):
        """Vérifie et débite les crédits voix (par minute)."""
        Tenant = self.env.get("doorway.tenant")
        if not Tenant:
            return True
        tenant = Tenant.get_tenant_for_company()
        if not tenant:
            return True
        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        engine = CreditEngine(self.env)
        check = engine.check_balance(tenant.id, "elevenlabs_voice", minutes)
        if not check["can_proceed"]:
            return False
        engine.debit_service(
            tenant.id,
            "elevenlabs_voice",
            quantity=minutes,
            description="ElevenLabs outbound",
        )
        return True

    def is_available(self):
        return bool(self._api_key())

    def create_call(self, agent, phone_number):
        """Démarre un appel sortant via l'agent ElevenLabs configuré."""
        if not self.is_available() or not agent.elevenlabs_agent_id:
            return {}
        if not self._guard_and_debit_elevenlabs():
            return {"error": "insufficient_credits"}
        headers = {
            "xi-api-key": self._api_key(),
            "content-type": "application/json",
        }
        payload = {
            "agent_id": agent.elevenlabs_agent_id,
            "customer_phone_number": phone_number,
        }
        try:
            resp = requests.post(
                f"{self.BASE}/convai/conversation/outbound_call",
                headers=headers,
                data=json.dumps(payload),
                timeout=30,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            _logger.warning("ElevenLabs create_call : %s", resp.text[:300])
        except Exception as error:  # noqa: BLE001
            _logger.warning("ElevenLabs create_call : %s", error)
        return {}

    def end_call(self, call_sid):
        """Termine un appel (selon API disponible)."""
        return True

    def get_transcript(self, conversation_id):
        """Récupère le transcript d'une conversation."""
        if not self.is_available() or not conversation_id:
            return ""
        headers = {"xi-api-key": self._api_key()}
        try:
            resp = requests.get(
                f"{self.BASE}/convai/conversations/{conversation_id}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("transcript") or json.dumps(data)[:8000]
        except Exception as error:  # noqa: BLE001
            _logger.warning("ElevenLabs transcript : %s", error)
        return ""
