# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPropertyPhotoCategory(models.Model):
    _name = "coins.property.photo.category"
    _description = "Catégorie de photo de lieu"
    _order = "sequence, id"

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        help="chambres | aires_communes | restauration | exterieur_piscine | bien_etre",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de catégorie photo doit être unique."),
    ]
