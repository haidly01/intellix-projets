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


class RenovationWebsiteLeadWebhookController(http.Controller):
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
                        return parsed
                except json.JSONDecodeError:
                    pass
        if kwargs:
            return dict(kwargs)
        return {}

    def _handle_pipeline_webhook(self, pipeline_key, kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)

        data = self._parse_payload(kwargs)
        webhook = request.env["renovation.website.lead.webhook"].sudo()

        token = (
            request.httprequest.headers.get("X-Renovation-Webhook-Token")
            or data.get("token")
            or data.get("webhook_token")
        )
        if token:
            data["token"] = token

        if not webhook._check_token(pipeline_key, data):
            return self._json_response(
                {"status": "error", "message": "Token webhook invalide ou manquant."},
                status=401,
            )

        try:
            result, status = webhook.create_lead_from_website_payload(pipeline_key, data)
        except Exception as exc:
            _logger.exception("Website lead webhook failed (%s)", pipeline_key)
            return self._json_response(
                {"status": "error", "message": str(exc)},
                status=500,
            )

        return self._json_response(result, status=status)

    @http.route(
        ["/api/portfolio/lead", "/api/renovation/lead/website", "/renovation/lead/website"],
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        website=False,
    )
    def website_lead_webhook_renovation(self, **kwargs):
        return self._handle_pipeline_webhook("renovation", kwargs)

    @http.route(
        ["/api/immobilier/lead/website", "/immobilier/lead/website"],
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        website=False,
    )
    def website_lead_webhook_immobilier(self, **kwargs):
        return self._handle_pipeline_webhook("immobilier", kwargs)

    @http.route(
        ["/api/marketing/lead/website", "/marketing/lead/website"],
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        website=False,
    )
    def website_lead_webhook_marketing(self, **kwargs):
        return self._handle_pipeline_webhook("marketing", kwargs)
