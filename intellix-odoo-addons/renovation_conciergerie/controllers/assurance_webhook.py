import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Renovation-Webhook-Token",
}


class RenovationAssuranceWebhookController(http.Controller):
    def _json_response(self, payload, status=200):
        return request.make_json_response(payload, status=status, headers=CORS_HEADERS)

    def _parse_payload(self, kwargs):
        req = request.httprequest
        if req.data:
            raw = req.data.decode("utf-8", errors="replace").strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        # Typeform : payload imbriqué possible {"form_response": {...}}
                        if "form_response" in parsed and isinstance(parsed["form_response"], dict):
                            flat = dict(parsed)
                            flat.update(parsed["form_response"])
                            return flat
                        return parsed
                except json.JSONDecodeError:
                    pass
        if kwargs:
            return dict(kwargs)
        return {}

    @http.route(
        "/assurance/lead",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def assurance_lead_webhook(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)

        data = self._parse_payload(kwargs)
        webhook = request.env["renovation.assurance.webhook"].sudo()

        token = (
            request.httprequest.headers.get("X-Renovation-Webhook-Token")
            or data.get("token")
            or data.get("webhook_token")
        )
        if token:
            data["token"] = token

        if not webhook._check_token(data):
            return self._json_response(
                {"status": "error", "message": "Token webhook invalide ou manquant."},
                status=401,
            )

        try:
            result, status = webhook.create_lead_from_payload(data)
        except Exception as exc:
            _logger.exception("Assurance lead webhook failed")
            return self._json_response(
                {"status": "error", "message": str(exc)}, status=500
            )

        return self._json_response(result, status=status)
