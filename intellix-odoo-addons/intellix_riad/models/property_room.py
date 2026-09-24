# -*- coding: utf-8 -*-

from odoo import fields, models


class CoinsPropertyRoomRiad(models.Model):
    _inherit = "coins.property.room"

    emplacement = fields.Selection(
        [
            ("etage", "Étage"),
            ("rdc", "RDC"),
        ],
        string="Emplacement",
    )
    currency_id = fields.Many2one(
        related="property_id.currency_id",
        store=True,
        readonly=True,
    )
    price_per_night = fields.Monetary(
        string="Tarif / nuit (PDJ inclus)",
        currency_field="currency_id",
    )
    breakfast_included = fields.Boolean(
        string="Petit-déjeuner inclus",
        default=True,
    )
