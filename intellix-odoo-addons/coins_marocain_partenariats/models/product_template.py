# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    coins_commission_pct = fields.Float(
        string="Commission Coins (%)",
        digits=(16, 2),
        help="Pourcentage à reporter sur la fiche partenaire. "
        "0 = pas une ligne de commission (forfait / setup).",
    )
