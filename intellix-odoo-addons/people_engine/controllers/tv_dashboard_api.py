# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class PeopleEngineTVController(http.Controller):

    @http.route(
        "/people-engine/tv/<string:token>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def tv_display(self, token, **kwargs):
        config = (
            request.env["pe.tv.config"]
            .sudo()
            .search([("public_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not config:
            return request.not_found()
        return request.render(
            "people_engine.tv_display_template",
            {
                "config": config,
                "token": token,
                "refresh_interval": config.refresh_interval or 300,
            },
        )

    @http.route(
        "/people-engine/tv/data/<string:token>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def tv_data(self, token, **kwargs):
        config = (
            request.env["pe.tv.config"]
            .sudo()
            .search([("public_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not config:
            return request.make_response(
                json.dumps({"error": "invalid_token"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )
        payload = request.env["pe.tv.dashboard.service"].sudo().get_tv_payload(
            config
        )
        return request.make_response(
            json.dumps(payload, default=str),
            headers=[("Content-Type", "application/json")],
        )
