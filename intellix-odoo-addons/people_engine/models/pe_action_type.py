# -*- coding: utf-8 -*-
from odoo import fields, models


class PeopleEngineActionType(models.Model):
    _name = "pe.action.type"
    _description = "Type d'action RH (référence juridique)"
    _order = "name"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("unique(code)", "Le code action doit être unique.")
