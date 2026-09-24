# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayBrandToneTag(models.Model):
    _name = "doorway.brand.tone.tag"
    _description = "Tag ton de marque"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer(string="Couleur")
