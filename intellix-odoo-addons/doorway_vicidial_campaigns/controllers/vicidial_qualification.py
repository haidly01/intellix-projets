# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class VicidialQualificationController(http.Controller):

    @http.route(
        "/doorway/vicidial/qualification/poll",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def poll(self, **kwargs):
        if not request.env.user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_qualifier"
        ):
            return request.make_response(
                json.dumps({"event": "idle", "reason": "no_access"}),
                headers=[("Content-Type", "application/json")],
            )
        result = (
            request.env["doorway.vicidial.call.sync"]
            .sudo()
            .sync_for_current_user()
        )
        return request.make_response(
            json.dumps(result),
            headers=[("Content-Type", "application/json")],
        )
