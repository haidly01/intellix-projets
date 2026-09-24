# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request

from .json_utils import json_dumps_safe


class VicidialQualificationHubController(http.Controller):

    def _check_access(self):
        return request.env.user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_qualifier"
        )

    @http.route(
        "/doorway/vicidial/qualification/hub",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def hub_data(
        self,
        date_from=None,
        date_to=None,
        campaign_vicidial_id=None,
        campaign_state=None,
        **kwargs,
    ):
        if not self._check_access():
            return request.make_response(
                json.dumps({"error": "no_access"}),
                headers=[("Content-Type", "application/json")],
                status=403,
            )
        data = (
            request.env["crm.lead"]
            .sudo()
            .get_qualification_hub_data(
                date_from=date_from,
                date_to=date_to,
                campaign_vicidial_id=campaign_vicidial_id or None,
                campaign_state=campaign_state or None,
            )
        )
        return request.make_response(
            json_dumps_safe(data),
            headers=[("Content-Type", "application/json")],
        )
