# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VicidialCampaignWebhook(http.Controller):
    def _webhook_key(self):
        icp = request.env["ir.config_parameter"].sudo()
        return icp.get_param("doorway_vicidial_campaigns.webhook_key") or icp.get_param(
            "doorway_agents_dashboard.webhook_token"
        )

    def _check_key(self):
        expected = self._webhook_key()
        provided = request.httprequest.headers.get("X-Doorway-Key")
        if not provided:
            provided = request.params.get("token")
        return expected and provided == expected

    def _json_body(self):
        raw = request.httprequest.get_data(as_text=True) or ""
        if not raw:
            return request.params or {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return request.params or {}

    def _handle_call_event(self):
        if not self._check_key():
            return request.make_response(
                json.dumps({"error": "unauthorized"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )
        payload = self._json_body()
        if isinstance(payload, list):
            payloads = payload
        else:
            payloads = [payload]
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(request.env(su=True))
        for item in payloads:
            if item:
                svc.upsert_call_from_webhook(item)
        return request.make_response(
            json.dumps({"status": "ok", "processed": len(payloads)}),
            headers=[("Content-Type", "application/json")],
        )

    @http.route(
        "/api/vicidial/webhook/call",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_call(self, **kwargs):
        return self._handle_call_event()

    @http.route(
        "/doorway/vicidial/webhook/call",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_call_legacy(self, **kwargs):
        return self._handle_call_event()
