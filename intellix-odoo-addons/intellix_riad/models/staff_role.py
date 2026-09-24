# -*- coding: utf-8 -*-

from odoo import fields, models


class IntellixRiadStaffRole(models.Model):
    _name = "intellix.riad.staff.role"
    _description = "Rôle personnel hébergement"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    legacy_role = fields.Selection(
        [
            ("reception", "Réception"),
            ("menage", "Ménage"),
            ("cuisine", "Cuisine"),
            ("wellness", "Bien-être / beauté"),
            ("restaurant", "Service restaurant"),
        ],
        string="Poste historique",
    )
    wellness_type_code = fields.Char(
        string="Code soin",
        help="Si renseigné, ce rôle ouvre la dispo dans le planning bien-être.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de rôle doit être unique."),
    ]
