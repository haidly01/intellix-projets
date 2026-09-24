# -*- coding: utf-8 -*-
"""Favoris carte — rattachés au Carnet du Voyageur (réutilisable app)."""
import re
import unicodedata

from odoo import api, fields, models


def _slugify(text):
    raw = unicodedata.normalize("NFKD", text or "")
    raw = "".join(c for c in raw if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug or "lieu"


class CoinsCarnetFavori(models.Model):
    _name = "coins.carnet.favori"
    _description = "Favori carte (Carnet du Voyageur)"
    _order = "create_date desc, id desc"
    _rec_name = "property_id"

    carnet_id = fields.Many2one(
        "coins.carnet",
        string="Carnet",
        required=True,
        ondelete="cascade",
        index=True,
    )
    property_id = fields.Many2one(
        "coins.property",
        string="Lieu",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        related="carnet_id.partner_id",
        store=True,
        index=True,
    )

    _sql_constraints = [
        (
            "carnet_property_uniq",
            "unique(carnet_id, property_id)",
            "Ce lieu est déjà en favori sur ce carnet.",
        ),
    ]

    @api.model
    def _carnet_from_token(self, token):
        token = (token or "").strip()
        if not token or len(token) < 8:
            return self.env["coins.carnet"]
        return self.env["coins.carnet"].sudo().search([
            ("portal_token", "=", token),
            ("active", "=", True),
        ], limit=1)

    @api.model
    def list_for_token(self, token):
        carnet = self._carnet_from_token(token)
        if not carnet:
            return None
        rows = self.sudo().search([("carnet_id", "=", carnet.id)])
        out = []
        for r in rows:
            prop = r.property_id
            if (
                not prop
                or not prop.active
                or not prop.is_carte_public()
            ):
                continue
            out.append({
                "id": r.id,
                "property_id": prop.id,
                "name": prop.name,
                "slug": _slugify(prop.name),
                "detail_url": "/lieux/%s" % _slugify(prop.name),
            })
        return out

    @api.model
    def toggle_for_token(self, token, property_id):
        """Ajoute ou retire. None = token invalide."""
        carnet = self._carnet_from_token(token)
        if not carnet:
            return None
        try:
            pid = int(property_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "property_id"}
        prop = self.env["coins.property"].sudo().browse(pid).exists()
        if (
            not prop
            or not prop.active
            or prop.state != "active"
            or not prop.is_carte_public()
        ):
            return {"ok": False, "error": "not_found"}
        existing = self.sudo().search([
            ("carnet_id", "=", carnet.id),
            ("property_id", "=", prop.id),
        ], limit=1)
        if existing:
            existing.unlink()
            return {"ok": True, "favorited": False, "property_id": prop.id}
        self.sudo().create({
            "carnet_id": carnet.id,
            "property_id": prop.id,
        })
        return {"ok": True, "favorited": True, "property_id": prop.id}

    @api.model
    def property_ids_for_token(self, token):
        carnet = self._carnet_from_token(token)
        if not carnet:
            return None
        return self.sudo().search([("carnet_id", "=", carnet.id)]).mapped(
            "property_id"
        ).ids
