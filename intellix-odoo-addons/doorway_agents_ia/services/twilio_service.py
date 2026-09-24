# -*- coding: utf-8 -*-
"""Twilio — appels, AMD (répondeur) et webhooks."""
import logging

_logger = logging.getLogger(__name__)


class TwilioService:
    """Encapsule le client Twilio (mode dégradé sans credentials)."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _config(self):
        return {
            "sid": self._icp.get_param("doorway_agents_ia.twilio_account_sid")
            or self._icp.get_param("renovation_conciergerie.twilio_account_sid", ""),
            "token": self._icp.get_param("doorway_agents_ia.twilio_auth_token")
            or self._icp.get_param("renovation_conciergerie.twilio_auth_token", ""),
            "from": self._icp.get_param("doorway_agents_ia.twilio_phone_number")
            or self._icp.get_param("renovation_conciergerie.twilio_from_number", ""),
            "base_url": self._icp.get_param("web.base.url", ""),
        }

    def is_available(self):
        c = self._config()
        return bool(c["sid"] and c["token"])

    def _client(self):
        from twilio.rest import Client

        c = self._config()
        return Client(c["sid"], c["token"])

    def _guard_twilio_credits(self, minutes=1):
        """Vérifie le solde avant un appel Twilio."""
        Tenant = self.env.get("doorway.tenant")
        if not Tenant:
            return True
        tenant = Tenant.get_tenant_for_company()
        if not tenant:
            return True
        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        engine = CreditEngine(self.env)
        check = engine.check_balance(tenant.id, "twilio_call", minutes)
        return check["can_proceed"]

    def _amd_callback_url(self):
        base = self._config()["base_url"].rstrip("/")
        return "%s/doorway/agents/webhook/amd" % base

    def make_call(self, to_number, session):
        """Passe un appel sortant avec détection répondeur (AMD)."""
        return self.make_outbound_call(to_number, session.agent_id.id if session.agent_id else None, session.lead_id.id if session.lead_id else None, session=session)

    def make_outbound_call(self, phone_number, agent_id=None, lead_id=None, session=None):
        """
        Appel sortant + AMD pour éviter ElevenLabs sur les répondeurs.
        Économie estimée : 30-40% sur les minutes vocales.
        """
        if not self.is_available():
            return False
        if not self._guard_twilio_credits():
            return False
        c = self._config()
        base = c["base_url"].rstrip("/")
        try:
            client = self._client()
            kwargs = {
                "to": phone_number,
                "from_": c["from"],
                "url": "%s/doorway/agents/webhook/twiml" % base,
                "status_callback": "%s/doorway/agents/webhook/twilio" % base,
                "status_callback_event": ["initiated", "ringing", "answered", "completed"],
                "record": True,
                "machine_detection": "DetectMessageEnd",
                "machine_detection_timeout": 4,
                "machine_detection_speech_threshold": 2400,
                "machine_detection_speech_end_threshold": 1200,
                "machine_detection_silence_timeout": 3000,
                "async_amd": True,
                "async_amd_status_callback": self._amd_callback_url(),
                "async_amd_status_callback_method": "POST",
            }
            call = client.calls.create(**kwargs)
            if session:
                session.sudo().write({"twilio_call_sid": call.sid, "call_status": "initiated"})
            return call.sid
        except Exception as error:  # noqa: BLE001
            _logger.warning("Twilio make_outbound_call : %s", error)
            return False

    def get_session_by_call_sid(self, call_sid):
        """Retourne la session Odoo liée au CallSid Twilio."""
        return self.env["doorway.call.session"].sudo().search(
            [("twilio_call_sid", "=", call_sid)], limit=1
        )

    def handle_amd_webhook(self, call_sid, answered_by):
        """
        Webhook AMD Twilio.
        answered_by : human | machine | machine_start | unknown | fax
        """
        session = self.get_session_by_call_sid(call_sid)
        if not session:
            return False
        machine_values = (
            "machine",
            "machine_start",
            "machine_end_beep",
            "machine_end_silence",
            "machine_end_other",
            "fax",
        )
        if answered_by in machine_values:
            try:
                self._client().calls(call_sid).update(status="completed")
            except Exception as error:  # noqa: BLE001
                _logger.warning("Twilio AMD hangup : %s", error)
            session.write(
                {
                    "call_status": "voicemail",
                    "coaching_notes": "Répondeur détecté — appel terminé automatiquement",
                }
            )
            return True
        if answered_by == "human":
            self.connect_elevenlabs_agent(call_sid, session.agent_id)
        return True

    def connect_elevenlabs_agent(self, call_sid, agent):
        """Connecte l'agent ElevenLabs après confirmation humain (AMD)."""
        if not agent:
            return False
        try:
            from odoo.addons.doorway_agents_ia.services.elevenlabs_service import ElevenlabsService

            session = self.get_session_by_call_sid(call_sid)
            phone = session.to_number or session.from_number if session else None
            if phone:
                ElevenlabsService(self.env).create_call(agent, phone)
            return True
        except Exception as error:  # noqa: BLE001
            _logger.warning("ElevenLabs connect après AMD : %s", error)
            return False

    def receive_call(self, post_data):
        """Traite un appel entrant (depuis webhook)."""
        sid = post_data.get("CallSid")
        session = self.env["doorway.call.session"].sudo().search(
            [("twilio_call_sid", "=", sid)], limit=1
        )
        if not session:
            session = self.env["doorway.call.session"].sudo().create(
                {
                    "twilio_call_sid": sid,
                    "call_status": post_data.get("CallStatus", "ringing"),
                    "from_number": post_data.get("From"),
                    "to_number": post_data.get("To"),
                }
            )
        else:
            session.write({"call_status": post_data.get("CallStatus", session.call_status)})
        return session

    def transfer_call(self, call_sid, to_number):
        """Transfère un appel en cours."""
        if not self.is_available():
            return False
        try:
            client = self._client()
            client.calls(call_sid).update(
                twiml="<Response><Dial>%s</Dial></Response>" % to_number
            )
            return True
        except Exception as error:  # noqa: BLE001
            _logger.warning("Twilio transfer : %s", error)
            return False

    def record_call(self, call_sid):
        """Active l'enregistrement sur un appel."""
        return bool(call_sid)
