# -*- coding: utf-8 -*-
from odoo import fields, models


class IntellixSupportStage(models.Model):
    _name = "intellix.support.stage"
    _description = "Étape ticket support"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string="Replié dans Kanban")
    is_closed = fields.Boolean(string="Clôturé")
    code = fields.Char(index=True)
