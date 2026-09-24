# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_billing_company_id = fields.Many2one(
        "res.company",
        string="Société de facturation",
        help=(
            "Remplace le routage automatique MA/CA pour ce contact. "
            "Utile pour les cas particuliers (filiale, facturation centralisée)."
        ),
        domain="[('x_intellix_accounting_region', 'in', ('ma', 'ca'))]",
    )
