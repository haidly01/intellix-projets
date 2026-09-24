# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request

from .json_utils import json_dumps_safe


class CallsCoachingDashboardController(http.Controller):

    @http.route(
        "/doorway/vicidial/calls/dashboard",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def dashboard_data(
        self,
        date_from=None,
        date_to=None,
        qualifications=None,
        campaign_vicidial_id=None,
        campaign_state=None,
        **kwargs,
    ):
        quals = None
        if qualifications and qualifications != "all":
            quals = [q.strip() for q in qualifications.split(",") if q.strip()]
        data = (
            request.env["crm.lead"]
            .sudo()
            .get_calls_coaching_dashboard(
                date_from=date_from or None,
                date_to=date_to or None,
                qualifications=quals,
                campaign_vicidial_id=campaign_vicidial_id or None,
                campaign_state=campaign_state or None,
            )
        )
        return request.make_response(
            json_dumps_safe(data),
            headers=[("Content-Type", "application/json")],
        )
