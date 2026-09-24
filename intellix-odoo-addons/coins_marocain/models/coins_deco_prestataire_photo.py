# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsDecoPrestatairePhoto(models.Model):
    _name = "coins.deco.prestataire.photo"
    _description = "Photo prestataire déco (Coins Marocain)"
    _order = "sequence, id"

    prestataire_id = fields.Many2one(
        "coins.deco.prestataire",
        string="Prestataire déco",
        required=True,
        ondelete="cascade",
        index=True,
    )
    image = fields.Image(string="Image", required=True, max_width=1920, max_height=1920)
    sequence = fields.Integer(string="Ordre", default=10)
    legende = fields.Char(string="Légende")
    theme_id = fields.Many2one(
        "coins.deco.prestataire.theme",
        string="Thème",
        required=True,
        ondelete="restrict",
        index=True,
        help="Obligatoire — au moins 3 photos par thème coché pour publier.",
    )
