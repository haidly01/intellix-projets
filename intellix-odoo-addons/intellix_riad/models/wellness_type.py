# -*- coding: utf-8 -*-

from odoo import fields, models


class IntellixRiadWellnessType(models.Model):
    _name = "intellix.riad.wellness.type"
    _description = "Type de soin bien-être"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    css_class = fields.Char(string="Classe CSS", default="massage")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de soin doit être unique."),
    ]
