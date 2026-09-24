# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_ORIGINS = (
    "https://coinsquebec.com",
    "https://www.coinsquebec.com",
    "https://intellixcrm.com",
    "https://www.intellixcrm.com",
)


class CoinsQuebecCarte(http.Controller):
    def _cors_headers(self):
        origin = request.httprequest.headers.get("Origin") or ""
        allow = origin if origin in CORS_ORIGINS else "https://coinsquebec.com"
        return {
            "Access-Control-Allow-Origin": allow,
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Accept, Content-Type",
            "Cache-Control": "no-store",
        }

    def _published(self):
        domain = [("publish_state", "=", "published"), ("active", "=", True)]
        demo_session = bool(request.session.get("mon_coin_demo"))
        if not demo_session:
            domain.append(("is_demo", "=", False))
        return (
            request.env["coins.quebec.partenariat"]
            .sudo()
            .search(domain)
        )

    @http.route(
        [
            "/carte",
            "/carte/",
            "/coins-quebec/carte",
            "/coins-quebec/carte/",
        ],
        type="http",
        auth="public",
        website=False,
    )
    def carte_page(self, **kw):
        listings = [rec.to_public_listing() for rec in self._published()]
        return request.render(
            "coins_quebec.carte_publique",
            {"listings": listings, "listings_json": json.dumps(listings)},
        )

    @http.route(
        [
            "/coins-quebec/api/public/listings",
            "/coins-quebec/carte/pins.json",
        ],
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
        website=False,
    )
    def public_listings(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=list(self._cors_headers().items()))
        recs = self._published()
        track = (kw.get("track") or "") == "1"
        listings = []
        for rec in recs:
            if track:
                rec.increment_pin_view()
            listings.append(rec.to_public_listing())
        body = json.dumps({"ok": True, "source": "odoo", "listings": listings})
        headers = self._cors_headers()
        headers["Content-Type"] = "application/json; charset=utf-8"
        return request.make_response(body, headers=list(headers.items()))

    @http.route(
        ["/coins-quebec/carte/photo/<int:photo_id>"],
        type="http",
        auth="public",
        website=False,
    )
    def public_photo(self, photo_id, **kw):
        photo = request.env["coins.quebec.partenariat.photo"].sudo().browse(photo_id)
        if (
            not photo.exists()
            or not photo.image
            or photo.partenariat_id.publish_state != "published"
        ):
            return request.not_found()
        import base64

        data = photo.image
        if isinstance(data, str):
            data = base64.b64decode(data)
        return request.make_response(
            data,
            headers=[
                ("Content-Type", "image/jpeg"),
                ("Cache-Control", "public, max-age=86400"),
            ],
        )

    @http.route(
        ["/coins-quebec/carte/click/<int:part_id>"],
        type="http",
        auth="public",
        methods=["POST", "GET"],
        csrf=False,
        website=False,
    )
    def track_click(self, part_id, **kw):
        rec = (
            request.env["coins.quebec.partenariat"]
            .sudo()
            .browse(part_id)
        )
        if rec.exists() and rec.publish_state == "published":
            rec.increment_pin_click()
        headers = self._cors_headers()
        headers["Content-Type"] = "application/json; charset=utf-8"
        return request.make_response(
            json.dumps({"ok": True}), headers=list(headers.items())
        )

    @http.route(
        ["/coins-quebec/fiche/<int:part_id>", "/coins-quebec/fiche/<int:part_id>/"],
        type="http",
        auth="public",
        website=False,
    )
    def public_fiche(self, part_id, **kw):
        rec = request.env["coins.quebec.partenariat"].sudo().browse(part_id)
        if not rec.exists() or rec.publish_state != "published":
            return request.not_found()
        if rec.is_demo and not request.session.get("mon_coin_demo"):
            return request.not_found()
        rec.increment_pin_click()
        return request.render(
            "coins_quebec.carte_fiche_publique",
            {"fiche": rec, "listing": rec.to_public_listing()},
        )
