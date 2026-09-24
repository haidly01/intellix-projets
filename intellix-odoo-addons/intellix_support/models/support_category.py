# -*- coding: utf-8 -*-
from odoo import fields, models


class IntellixSupportCategory(models.Model):
    _name = "intellix.support.category"
    _description = "Catégorie ticket support"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True)
    description = fields.Text()
    color = fields.Integer(string="Couleur")
    active = fields.Boolean(default=True)
