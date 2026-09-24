# -*- coding: utf-8 -*-

from odoo import fields, models


class BabinvestProject(models.Model):
    _name = "babinvest.project"
    _description = "Projet immobilier Bab Invest"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    market_id = fields.Many2one("babinvest.market", string="Marché", required=True)
    city = fields.Char()
    unit_price_min = fields.Monetary(string="Prix unité — min")
    unit_price_max = fields.Monetary(string="Prix unité — max")
    rental_yield_pct = fields.Float(string="Rendement locatif estimé (%)")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    description = fields.Text()
