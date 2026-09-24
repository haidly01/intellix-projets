# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PeopleEngineLegalWebhook(http.Controller):

    @http.route(
        "/people-engine/legal/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def receive_legal_update(self, **kwargs):
        secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("people_engine.webhook_secret", "")
        )
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get("X-PE-Signature", "")

        if secret:
            expected = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return request.make_response(
                    json.dumps({"error": "invalid_signature", "status": 401}),
                    headers=[("Content-Type", "application/json")],
                    status=401,
                )

        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return request.make_response(
                json.dumps({"error": "invalid_json"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        if not data.get("modifies_law", True) and "new_content" not in data:
            return request.make_response(
                json.dumps({"status": "skipped", "reason": "no_change"}),
                headers=[("Content-Type", "application/json")],
            )

        service = request.env["pe.legal.updater.service"].sudo()
        result = service.propose_article_update(
            article_code=data.get("article_code"),
            jurisdiction_code=data.get("jurisdiction_code", "QC"),
            new_content=data.get("new_content") or data.get("change_summary", ""),
            source_url=data.get("source_url", ""),
        )
        return request.make_response(
            json.dumps({"status": "ok", "result": result}, default=str),
            headers=[("Content-Type", "application/json")],
        )
