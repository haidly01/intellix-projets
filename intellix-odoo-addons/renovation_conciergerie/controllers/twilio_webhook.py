from odoo import fields, http
from odoo.http import request


class RenovationTwilioWebhookController(http.Controller):
    @http.route("/renovation/twilio/status", type="http", auth="public", methods=["POST"], csrf=False)
    def twilio_status_callback(self, **post):
        call_sid = post.get("CallSid")
        call_status = post.get("CallStatus")
        duration = post.get("CallDuration")
        model = request.env["renovation.twilio.call.log"].sudo()
        log = model.search([("twilio_call_sid", "=", call_sid)], limit=1)
        if log:
            vals = {"status": call_status or log.status}
            if call_status in ("completed", "failed", "busy", "no-answer", "canceled"):
                vals["ended_at"] = fields.Datetime.now()
            if duration and str(duration).isdigit():
                vals["duration_seconds"] = int(duration)
            log.write(vals)
        return http.Response("OK", status=200)

    @http.route("/renovation/twilio/recording", type="http", auth="public", methods=["POST"], csrf=False)
    def twilio_recording_callback(self, **post):
        call_sid = post.get("CallSid")
        model = request.env["renovation.twilio.call.log"].sudo()
        log = model.search([("twilio_call_sid", "=", call_sid)], limit=1)
        if log:
            log.write(
                {
                    "recording_sid": post.get("RecordingSid"),
                    "recording_url": post.get("RecordingUrl"),
                    "recording_status": post.get("RecordingStatus"),
                }
            )
        return http.Response("OK", status=200)

    @http.route("/renovation/twilio/twiml/outbound", type="http", auth="public", methods=["GET", "POST"], csrf=False)
    def twilio_twiml_outbound(self, **kwargs):
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR">Bonjour, ceci est un appel de suivi.</Say>
    <Record maxLength="120" playBeep="true"/>
</Response>"""
        return http.Response(twiml, content_type="text/xml; charset=utf-8", status=200)
