# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class IntellixRiadDashboardController(http.Controller):
    @http.route(
        "/intellix_riad/dashboard",
        type="json",
        auth="user",
    )
    def dashboard(self, establishment_id=None):
        return request.env["intellix.riad.dashboard"].get_dashboard_data(
            establishment_id
        )

    @http.route(
        "/intellix_riad/calendar",
        type="json",
        auth="user",
    )
    def calendar(self, establishment_id=None, days=14):
        return request.env["intellix.riad.dashboard"].get_calendar_data(
            establishment_id, days
        )
