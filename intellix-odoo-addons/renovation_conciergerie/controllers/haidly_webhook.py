# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, X-Haidly-Webhook-Token, X-Doorway-Key, X-Doorway-Token"
    ),
}


class RenovationHaidlyWebhookController(http.Controller):
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

    def _auth(self, data):
        token = (
            request.httprequest.headers.get("X-Haidly-Webhook-Token")
            or request.httprequest.headers.get("X-Doorway-Key")
            or data.get("token")
        )
        if token:
            data["token"] = token
        return request.env["renovation.haidly.webhook"].sudo()._check_token(data)

    @http.route(
        "/api/haidly/lead",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def haidly_lead_webhook(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.haidly.webhook"
            ].sudo().create_lead_from_webhook(data)
        except Exception:
            _logger.exception("Haidly lead webhook")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

    @http.route(
        "/api/haidly/lead/update",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def haidly_lead_update(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.haidly.webhook"
            ].sudo().update_lead_from_n8n(data)
        except Exception:
            _logger.exception("Haidly lead update")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

    @http.route(
        "/api/haidly/lead/<int:lead_id>",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def haidly_lead_get(self, lead_id, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.haidly.webhook"
            ].sudo().get_lead_context_for_n8n(lead_id)
        except Exception:
            _logger.exception("Haidly lead get")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)


    @http.route(
        ["/api/haidly/portfolio-lead", "/api/portfolio/lead"],
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def portfolio_lead_webhook(self, **kwargs):
        """Webhook central portfolio sites → pipeline Rénovation."""
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        token = (
            request.httprequest.headers.get("X-Renovation-Webhook-Token")
            or request.httprequest.headers.get("X-Haidly-Webhook-Token")
            or data.get("token")
            or data.get("webhook_token")
        )
        if token:
            data["token"] = token
        webhook = request.env["renovation.website.lead.webhook"].sudo()
        if not webhook._check_token("renovation", data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = webhook.create_lead_from_website_payload("renovation", data)
        except Exception:
            _logger.exception("Portfolio lead webhook")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

