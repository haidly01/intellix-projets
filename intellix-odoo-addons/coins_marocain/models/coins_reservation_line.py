# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsReservationLine(models.Model):
    _name = "coins.reservation.line"
    _description = "Ligne cross-sell réservation"
    _order = "id"

    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        required=True,
        ondelete="cascade",
        index=True,
    )
    code = fields.Char(string="Code pack", required=True)
    name = fields.Char(string="Libellé", required=True)
    qty = fields.Integer(string="Quantité", default=1, required=True)
    price_unit_cad = fields.Monetary(
        string="Prix unitaire CAD",
        currency_field="currency_id",
        required=True,
    )
    amount_cad = fields.Monetary(
        string="Montant CAD",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        related="reservation_id.currency_id",
        readonly=True,
    )

    @api.depends("price_unit_cad", "qty")
    def _compute_amount(self):
        for rec in self:
            rec.amount_cad = (rec.price_unit_cad or 0.0) * (rec.qty or 0)
