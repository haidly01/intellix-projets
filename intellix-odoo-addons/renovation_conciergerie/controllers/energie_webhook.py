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
        "Content-Type, X-Energie-Webhook-Token, X-Doorway-Key, X-Doorway-Token"
    ),
}


class RenovationEnergieWebhookController(http.Controller):
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
            request.httprequest.headers.get("X-Energie-Webhook-Token")
            or request.httprequest.headers.get("X-Doorway-Key")
            or data.get("token")
        )
        if token:
            data["token"] = token
        return request.env["renovation.energie.webhook"].sudo()._check_token(data)

    @http.route(
        "/api/energie/lead",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def energie_lead_webhook(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.energie.webhook"
            ].sudo().create_lead_from_webhook(data)
        except Exception:
            _logger.exception("Energie lead webhook")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

    @http.route(
        "/api/energie/lead/update",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def energie_lead_update(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.energie.webhook"
            ].sudo().update_lead_from_n8n(data)
        except Exception:
            _logger.exception("Energie lead update")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

    @http.route(
        "/api/energie/lead/<int:lead_id>",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def energie_lead_get(self, lead_id, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.energie.webhook"
            ].sudo().get_lead_context_for_n8n(lead_id)
        except Exception:
            _logger.exception("Energie lead get")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)
