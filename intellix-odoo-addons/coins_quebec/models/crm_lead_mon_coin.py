# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLeadMonCoin(models.Model):
    _inherit = "crm.lead"

    cq_partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        string="Fiche commerçant CQ",
        ondelete="set null",
        index=True,
        help="Lien portail Mon Coin → lead ITEX (team 112) ou Driven (team 94).",
    )
