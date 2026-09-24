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
        "Content-Type, X-Immo-Webhook-Token, X-Doorway-Key, X-Doorway-Token"
    ),
}


class RenovationMetaImmoWebhookController(http.Controller):
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
        webhook = request.env["renovation.meta.immo.webhook"].sudo()
        token = (
            request.httprequest.headers.get("X-Immo-Webhook-Token")
            or request.httprequest.headers.get("X-Doorway-Key")
            or request.httprequest.headers.get("X-Doorway-Token")
            or data.get("token")
        )
        if token:
            data["token"] = token
        return webhook._check_token(data)

    @http.route(
        "/api/immo/meta-lead",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def meta_lead_webhook(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.meta.immo.webhook"
            ].sudo().create_lead_from_meta(data)
        except Exception:
            _logger.exception("Meta immo lead webhook")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

    @http.route(
        "/api/immo/lead/update",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def meta_lead_update(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.meta.immo.webhook"
            ].sudo().update_lead_from_n8n(data)
        except Exception:
            _logger.exception("Meta immo lead update")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)

    @http.route(
        "/api/immo/lead/<int:lead_id>",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def meta_lead_get(self, lead_id, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        token = (
            request.httprequest.headers.get("X-Immo-Webhook-Token")
            or request.httprequest.headers.get("X-Doorway-Key")
        )
        if token:
            data["token"] = token
        if not self._auth(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, status=401
            )
        try:
            result, status = request.env[
                "renovation.meta.immo.webhook"
            ].sudo().get_lead_context_for_n8n(lead_id)
        except Exception:
            _logger.exception("Meta immo lead get")
            return self._json_response(
                {"status": "error", "message": "Erreur serveur."}, status=500
            )
        return self._json_response(result, status=status)
