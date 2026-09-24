# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, X-Marketing-Meta-Webhook-Token"
    ),
}


class RenovationMetaMarketingWebhookController(http.Controller):
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
        return dict(kwargs) if kwargs else {}

    @http.route(
        "/api/marketing/meta-lead",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def marketing_meta_lead(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)

        data = self._parse_payload(kwargs)
        webhook = request.env["renovation.meta.marketing.webhook"].sudo()

        token = (
            request.httprequest.headers.get("X-Marketing-Meta-Webhook-Token")
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
            result, status = webhook.create_lead_from_meta_payload(data)
        except Exception as exc:
            _logger.exception("Marketing Meta lead webhook failed")
            return self._json_response(
                {"status": "error", "message": str(exc)},
                status=500,
            )

        return self._json_response(result, status=status)
