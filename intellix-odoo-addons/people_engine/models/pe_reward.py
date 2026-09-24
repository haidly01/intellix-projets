# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEngineReward(models.Model):
    _name = "pe.reward"
    _description = "Récompense People Engine"
    _order = "name"

    name = fields.Char(required=True)
    reward_type = fields.Selection(
        [
            ("recognition", "Reconnaissance publique"),
            ("time_off", "Temps libre additionnel"),
            ("gift_card", "Carte cadeau"),
            ("bonus", "Prime financière"),
            ("training", "Formation au choix"),
            ("custom", "Récompense personnalisée"),
        ],
        required=True,
        default="recognition",
    )
    amount = fields.Float()
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    requires_financial_approval = fields.Boolean(
        compute="_compute_financial_approval", store=True
    )
    accounting_account_id = fields.Many2one(
        "account.account",
        string="Compte comptable",
        help="Compte pour les récompenses financières (si module Comptabilité actif).",
    )
    dg_approval_required = fields.Boolean(
        compute="_compute_financial_approval", store=True
    )
    active = fields.Boolean(default=True)

    @api.depends("reward_type", "amount")
    def _compute_financial_approval(self):
        for reward in self:
            reward.requires_financial_approval = reward.reward_type in (
                "bonus",
                "gift_card",
            ) or (reward.amount or 0) > 0
            reward.dg_approval_required = (reward.amount or 0) > 100
