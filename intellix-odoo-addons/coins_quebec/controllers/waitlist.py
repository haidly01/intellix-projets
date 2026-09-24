# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept",
}


class CoinsQuebecWaitlist(http.Controller):
    """Waitlist visiteurs → coins.quebec.voyageur (Nouveau). Pas le kanban partenariats."""

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status, headers=CORS_HEADERS)

    def _parse(self, kwargs):
        req = request.httprequest
        if req.data:
            raw = req.data.decode("utf-8", errors="replace").strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
        return dict(kwargs or {})

    @http.route(
        ["/api/waitlist", "/coins-quebec/api/waitlist"],
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        website=False,
    )
    def waitlist(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS_HEADERS)

        data = self._parse(kwargs)
        email = (data.get("email") or data.get("courriel") or "").strip().lower()
        name = (
            data.get("name")
            or data.get("nom")
            or data.get("company")
            or data.get("etablissement")
            or ""
        ).strip()
        contact_name = (
            data.get("contact_name")
            or data.get("contact")
            or data.get("full_name")
            or name
            or ""
        ).strip()
        phone = (data.get("phone") or data.get("telephone") or data.get("tel") or "").strip()
        city = (data.get("city") or data.get("ville") or "").strip()
        message = (data.get("message") or data.get("notes") or data.get("comment") or "").strip()

        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return self._json({"ok": False, "error": "email_requis"}, 400)

        track = (data.get("track") or "visiteur").strip()
        Voy = request.env["coins.quebec.voyageur"].sudo()
        existing = Voy.search([("email", "=ilike", email)], limit=1)
        note_line = "Waitlist site coinsquebec.com (%s)" % track
        if message:
            note_line = "%s\n%s" % (note_line, message)

        if existing:
            # Ne jamais changer Nouveau/Contacté/En RDV/Suivis/Entente.
            notes = existing.notes or ""
            if "Waitlist site coinsquebec.com" not in notes:
                existing.write({"notes": (notes + "\n\n" + note_line).strip()})
            return self._json({
                "ok": True,
                "status": "existing",
                "voyageur_id": existing.id,
                "stage": existing.stage,
            })

        vals = {
            "name": name or contact_name or email,
            "email": email,
            "phone": phone or False,
            "city": city or False,
            "stage": "nouveau",
            "region": "montreal",
            "type_sejour": "mixte",
            "notes": note_line,
        }
        rec = Voy.create(vals)
        return self._json({
            "ok": True,
            "status": "created",
            "voyageur_id": rec.id,
            "stage": rec.stage,
        })
