# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPartnerInterest(models.Model):
    """Tag d'intérêt voyage — sélection multiple sur la fiche contact (qualification)."""

    _name = "coins.partner.interest"
    _description = "Intérêt voyage (Coins Marocain)"
    _order = "sequence, name"

    name = fields.Char(string="Intérêt", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
