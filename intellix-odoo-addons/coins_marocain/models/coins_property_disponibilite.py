# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPropertyDisponibilite(models.Model):
    _name = "coins.property.disponibilite"
    _description = "Période disponible (Coins Marocain)"
    _order = "date_debut, id"

    property_id = fields.Many2one(
        "coins.property",
        string="Propriété",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_debut = fields.Date(string="Début", required=True, index=True)
    date_fin = fields.Date(string="Fin", required=True, index=True)
    name = fields.Char(string="Libellé", compute="_compute_name")

    def _compute_name(self):
        for rec in self:
            prop = rec.property_id.name or ""
            if rec.date_debut and rec.date_fin:
                rec.name = "%s : %s → %s" % (prop, rec.date_debut, rec.date_fin)
            else:
                rec.name = prop or "Disponibilité"
