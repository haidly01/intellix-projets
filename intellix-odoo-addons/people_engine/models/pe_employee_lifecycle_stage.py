# -*- coding: utf-8 -*-
from odoo import fields, models


class PeEmployeeLifecycleStage(models.Model):
    _name = "pe.employee.lifecycle.stage"
    _description = "Stade du cycle de vie employé"
    _order = "sequence, id"

    name = fields.Char(string="Libellé", required=True, translate=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Couleur")
    is_arrival = fields.Boolean(
        string="Stade d'arrivée",
        help="Utilisé pour suggérer le pack documents d'intégration.",
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "unique(code)",
        "Le code de stade doit être unique.",
    )
