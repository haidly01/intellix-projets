# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class MyCoachingController(http.Controller):

    def _check_qualifier(self):
        return request.env.user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_qualifier"
        )

    @http.route(
        "/doorway/vicidial/coaching/my",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def my_coaching(self, date_from=None, date_to=None, **kwargs):
        if not self._check_qualifier():
            return request.make_response(
                json.dumps({"error": "forbidden"}),
                status=403,
                headers=[("Content-Type", "application/json")],
            )
        data = (
            request.env["doorway.vicidial.agent.session"]
            .get_my_coaching_data(
                date_from=date_from or None,
                date_to=date_to or None,
            )
        )
        return request.make_response(
            json.dumps(data),
            headers=[("Content-Type", "application/json")],
        )

    @http.route(
        "/doorway/vicidial/coaching/mark_read/<int:call_id>",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def mark_read(self, call_id, **kwargs):
        if not self._check_qualifier():
            return request.make_response(
                json.dumps({"status": "forbidden"}),
                status=403,
                headers=[("Content-Type", "application/json")],
            )
        result = (
            request.env["doorway.vicidial.agent.session"]
            .mark_coaching_call_read(call_id)
        )
        return request.make_response(
            json.dumps(result),
            headers=[("Content-Type", "application/json")],
        )
