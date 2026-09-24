# -*- coding: utf-8 -*-
"""Portail chauffeur — stub reconstruit."""
from odoo import http
from odoo.http import request

class CoinsDriverPortal(http.Controller):
    @http.route(["/coins/driver/<string:token>", "/coins/driver/<string:token>/"], type="http", auth="public", website=False, csrf=False)
    def driver_home(self, token, **kw):
        return request.make_response(
            "<h1>Portail chauffeur</h1><p>Module en restauration. Contactez l'équipe Coins Marocain.</p>",
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
