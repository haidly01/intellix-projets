# -*- coding: utf-8 -*-
"""API Agents IA — analyse Claude (Module Performance)."""
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS"}


class IntellixAgentApiController(http.Controller):
    @http.route(
        "/api/intellix/agent/analyze",
        type="http",
        auth="user",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def agent_analyze(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        raw = request.httprequest.data.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return request.make_json_response(
                {"status": "error", "message": "JSON invalide."}, status=400
            )
        Profile = request.env["doorway.agent.profile"]
        result = Profile.performance_analyze_api(
            data.get("agent_id"),
            transcriptions=data.get("transcriptions"),
            current_prompt=data.get("current_prompt"),
        )
        status = 200 if result.get("status") == "ok" else 404
        return request.make_json_response(result, status=status, headers=CORS)
