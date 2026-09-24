# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request

from .json_utils import json_dumps_safe


class SupervisorDashboardController(http.Controller):

    def _check_supervisor(self):
        return request.env.user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_supervisor"
        )

    @http.route(
        "/doorway/vicidial/supervisor/dashboard",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def supervisor_dashboard(
        self,
        date_from=None,
        date_to=None,
        campaign_vicidial_id=None,
        campaign_state=None,
        **kwargs,
    ):
        if not self._check_supervisor():
            return request.make_response(
                json.dumps({"error": "forbidden"}),
                status=403,
                headers=[("Content-Type", "application/json")],
            )
        data = request.env["doorway.vicidial.agent.session"].get_supervisor_dashboard_data(
            date_from=date_from or None,
            date_to=date_to or None,
            campaign_vicidial_id=campaign_vicidial_id or None,
            campaign_state=campaign_state or None,
        )
        return request.make_response(
            json_dumps_safe(data),
            headers=[("Content-Type", "application/json")],
        )
