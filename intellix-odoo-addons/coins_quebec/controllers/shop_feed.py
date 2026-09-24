# -*- coding: utf-8 -*-
"""TikTok Shop Coins Québec — retiré. Pas de spec vide en ligne."""
from odoo import http
from odoo.http import request

_GONE = (
    "TikTok Shop retiré — non disponible au Maroc ni au Canada. "
    "Pas de flux Coins Québec.\n"
)


class CoinsQuebecShopFeed(http.Controller):
    @http.route(
        [
            "/api/coins-quebec/feeds/produits.json",
            "/feeds/coinsquebec-produits.json",
        ],
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def canonical_produits_json(self, **kwargs):
        resp = request.make_response(
            _GONE,
            headers=[
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Cache-Control", "no-store, no-cache, must-revalidate"),
            ],
        )
        resp.status_code = 410
        return resp
