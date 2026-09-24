# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Callcenter-Webhook-Token",
}


class CallcenterProspectingApi(http.Controller):
    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status, headers=CORS)

    def _parse(self, kwargs):
        req = request.httprequest
        if req.data:
            raw = req.data.decode("utf-8", errors="replace").strip()
            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass
        return dict(kwargs) if kwargs else {}

    def _check_token(self, data):
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_callcenter_prospecting.webhook_token", "")
        )
        if not expected:
            return True
        token = (
            request.httprequest.headers.get("X-Callcenter-Webhook-Token")
            or data.get("token")
            or data.get("webhook_token")
        )
        return token == expected

    @http.route(
        "/api/callcenter/prospects/ingest",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def ingest(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        data = self._parse(kwargs)
        if not self._check_token(data):
            return self._json({"ok": False, "error": "Token invalide"}, 403)
        Prospect = request.env["doorway.callcenter.prospect"].sudo()
        rows = data.get("prospects") or data.get("rows") or [data]
        results = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            results.append(Prospect.ingest_from_dict(row))
        return self._json({"ok": True, "results": results, "count": len(results)})

    @http.route(
        "/api/callcenter/prospects/validate",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def validate_batch(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        data = self._parse(kwargs)
        if not self._check_token(data):
            return self._json({"ok": False, "error": "Token invalide"}, 403)
        Prospect = request.env["doorway.callcenter.prospect"].sudo()
        domain = [("status", "=", "NEW")]
        if data.get("ids"):
            domain = [("id", "in", data["ids"])]
        if data.get("country"):
            domain.append(("country", "=", data["country"]))
        recs = Prospect.search(domain, limit=int(data.get("limit") or 50))
        recs.action_validate_twilio()
        for rec in recs:
            if rec.twilio_valid and not rec.crm_lead_id:
                rec._create_crm_lead()
        landlines = recs.filtered(lambda r: (r.line_type or "").lower() == "landline")
        return self._json(
            {
                "ok": True,
                "validated": len(recs),
                "whatsapp_ok": len(recs.filtered("whatsapp_capable")),
                "landlines": len(landlines),
            }
        )

    @http.route(
        "/api/callcenter/campaign/send-j0",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def send_j0(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        data = self._parse(kwargs)
        if not self._check_token(data):
            return self._json({"ok": False, "error": "Token invalide"}, 403)
        Prospect = request.env["doorway.callcenter.prospect"].sudo()
        domain = [("status", "=", "NEW"), ("contacted_j0", "=", False)]
        if data.get("country"):
            domain.append(("country", "=", data["country"]))
        recs = Prospect.search(domain, limit=int(data.get("limit") or 100))
        sent = recs.action_send_j0()
        return self._json({"ok": True, "sent": sent, "candidates": len(recs)})

    @http.route(
        "/api/callcenter/extraction/import",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def import_extraction(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        data = self._parse(kwargs)
        if not self._check_token(data):
            return self._json({"ok": False, "error": "Token invalide"}, 403)
        campagne_id = data.get("campagne_id") or data.get("extraction_campaign_id")
        if not campagne_id:
            return self._json({"ok": False, "error": "campagne_id requis"}, 400)
        result = (
            request.env["doorway.callcenter.prospect"]
            .sudo()
            .import_from_leads_bruts(int(campagne_id), limit=int(data.get("limit") or 500))
        )
        return self._json(result)

    @http.route(
        "/api/callcenter/stats",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def stats(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        Prospect = request.env["doorway.callcenter.prospect"].sudo()
        return self._json(
            {
                "total": Prospect.search_count([]),
                "whatsapp_ok": Prospect.search_count([("whatsapp_capable", "=", True)]),
                "landlines": Prospect.search_count([("status", "=", "LANDLINE")]),
                "contacted_j0": Prospect.search_count([("contacted_j0", "=", True)]),
                "qualified": Prospect.search_count([("status", "=", "QUALIFIED")]),
                "human_replies": Prospect.search_count(
                    [("reply_intent", "=", "INTERESTED")]
                ),
            }
        )
