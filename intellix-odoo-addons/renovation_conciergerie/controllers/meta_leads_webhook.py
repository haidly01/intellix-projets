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
        "Content-Type, X-Meta-Leads-Token, X-Doorway-Key"
    ),
}


class RenovationMetaLeadsWebhookController(http.Controller):
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

    def _check_routing_token(self, data):
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_leads_routing_token")
        )
        if not expected:
            return True
        provided = (
            request.httprequest.headers.get("X-Meta-Leads-Token")
            or request.httprequest.headers.get("X-Doorway-Key")
            or data.get("token")
        )
        return provided == expected

    @http.route(
        "/api/meta/leads/resolve",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def meta_leads_resolve(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        data = self._parse_payload(kwargs)
        if not self._check_routing_token(data):
            return self._json_response(
                {"status": "error", "message": "Token invalide."}, 403
            )
        route = (
            request.env["renovation.meta.leads.routing"]
            .sudo()
            .resolve_route(data)
        )
        return self._json_response(route, 200)

    @http.route(
        "/api/meta/leads/pages",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def meta_leads_pages(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)
        rows = (
            request.env["renovation.meta.leads.routing"]
            .sudo()
            .list_pages_summary()
        )
        return self._json_response({"status": "ok", "pages": rows}, 200)
