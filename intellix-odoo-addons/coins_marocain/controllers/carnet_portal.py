# -*- coding: utf-8 -*-
"""Portail Carnet — stub reconstruit."""
from odoo import http
from odoo.http import request

class CoinsCarnetPortal(http.Controller):
    @http.route(["/coins/carnet/<string:token>", "/coins/carnet/lookup"], type="http", auth="public", website=False, csrf=False)
    def carnet_home(self, token=None, **kw):
        return request.make_response(
            "<h1>Carnet du Voyageur</h1><p>Module en restauration.</p>",
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
