# -*- coding: utf-8 -*-

from odoo import fields, models


class BabinvestMarket(models.Model):
    _name = "babinvest.market"
    _description = "Marché Bab Invest (Marrakech, Dubaï, Portugal...)"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    country_id = fields.Many2one("res.country")
    project_ids = fields.One2many("babinvest.project", "market_id", string="Projets")
