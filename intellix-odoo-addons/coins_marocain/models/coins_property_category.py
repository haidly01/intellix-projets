# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPropertyCategory(models.Model):
    _name = "coins.property.category"
    _description = "Catégorie de lieu (Coins Marocain)"
    _order = "sequence, name"

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        help="decouverte | privatisation | evenements | bien_etre | hebergement",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string="Description")

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de catégorie doit être unique."),
    ]
