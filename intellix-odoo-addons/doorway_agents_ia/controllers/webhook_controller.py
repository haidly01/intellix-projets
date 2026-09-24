# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from odoo.addons.doorway_agents_ia.services.twilio_service import TwilioService
from odoo.addons.doorway_agents_ia.services.vicidial_service import VicidialService

_logger = logging.getLogger(__name__)


class DoorwayAgentsWebhookController(http.Controller):
    @http.route(
        "/doorway/agents/webhook/twilio",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def twilio_webhook(self, **post):
        """Réception événements Twilio : statut, transcript, fin d'appel."""
        try:
            session = TwilioService(request.env).receive_call(post)
            status = post.get("CallStatus") or session.call_status
            if status:
                session.write({"call_status": status})

            transcript = post.get("TranscriptionText") or post.get("SpeechResult")
            if transcript:
                session.write(
                    {"transcript": (session.transcript or "") + "\n" + transcript}
                )

            if session.transcript and session.call_status in ("in-progress", "answered"):
                last = session.last_coaching_at
                if not last or last < fields.Datetime.now() - timedelta(seconds=14):
                    session.run_realtime_coaching()

            if status in ("completed", "failed", "busy", "no-answer", "canceled"):
                if session.call_status != "voicemail":
                    session.finalize_call()
                else:
                    VicidialService(request.env).sync_with_odoo()
        except Exception as error:  # noqa: BLE001
            _logger.exception("Webhook Twilio Agents IA : %s", error)
        return http.Response("OK", status=200)

    @http.route(
        "/doorway/agents/webhook/twiml",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def twilio_twiml(self, **kwargs):
        """TwiML minimal pour appels sortants Doorway."""
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-CA">Bonjour, vous êtes en contact avec l'Agence Doorway.</Say>
    <Gather input="speech" language="fr-CA" speechTimeout="auto"
            action="/doorway/agents/webhook/twilio" method="POST"/>
    <Record maxLength="3600" playBeep="false" recordingStatusCallback="/doorway/agents/webhook/twilio"/>
</Response>"""
        return http.Response(twiml, content_type="text/xml; charset=utf-8", status=200)

    @http.route(
        "/doorway/agents/webhook/amd",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def twilio_amd_webhook(self, **post):
        """Détection répondeur Twilio — ne pas lancer ElevenLabs si machine."""
        try:
            TwilioService(request.env).handle_amd_webhook(
                post.get("CallSid"),
                post.get("AnsweredBy") or post.get("answered_by"),
            )
        except Exception as error:  # noqa: BLE001
            _logger.exception("Webhook AMD : %s", error)
        return http.Response("OK", status=200)

    @http.route(
        "/doorway/agents/webhook/lead-qualified",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def lead_qualified_webhook(self, lead_id, pipeline=None):
        """Webhook Odoo → n8n / assignation campagne VICIdial."""
        lead = request.env["crm.lead"].browse(int(lead_id))
        if lead.exists():
            lead.action_assign_vicidial_campaign()
        return {"ok": True, "lead_id": lead_id}
