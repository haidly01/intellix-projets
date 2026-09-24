# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEnginePrimeRule(models.Model):
    _name = "pe.prime.rule"
    _description = "Règle de prime People Engine"
    _order = "name"

    name = fields.Char(required=True)
    is_active = fields.Boolean(default=True)
    trigger_type = fields.Selection(
        [
            ("score_threshold", "Score global atteint"),
            ("objective_hit", "Objectif complété"),
            ("badge_earned", "Badge obtenu"),
            ("path_completed", "Parcours formation complété"),
            ("challenge_won", "Défi d'équipe gagné"),
            ("period_top", "Meilleur score de la période"),
            ("manual", "Attribution manuelle"),
        ],
        required=True,
        default="score_threshold",
    )
    trigger_value = fields.Float()
    trigger_badge_id = fields.Many2one("pe.badge")
    calculation_method = fields.Selection(
        [
            ("fixed", "Montant fixe"),
            ("percent_salary", "% du salaire mensuel"),
            ("per_point", "Par point de score"),
            ("tiered", "Paliers progressifs"),
        ],
        default="fixed",
        required=True,
    )
    amount_fixed = fields.Float()
    amount_percent = fields.Float(help="% du salaire mensuel")
    tiered_config = fields.Text(
        help='JSON : [{"min": 80, "max": 89, "amount": 200}]'
    )
    frequency = fields.Selection(
        [
            ("once", "Une seule fois"),
            ("monthly", "Mensuelle"),
            ("quarterly", "Trimestrielle"),
            ("annual", "Annuelle"),
        ],
        default="quarterly",
    )
    accounting_account_id = fields.Many2one(
        "account.account",
        string="Compte de charge",
        required=True,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Compte analytique",
    )
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('type', '=', 'general')]",
    )
    max_amount_per_employee = fields.Float(default=5000.0)
    max_total_budget = fields.Float(default=50000.0)
    requires_manager = fields.Boolean(default=True)
    requires_hr = fields.Boolean(default=True)
    requires_dg = fields.Boolean(default=True)
    requires_accounting = fields.Boolean(default=True)

    @api.model
    def _seed_default_rules(self):
        if self.search_count([]):
            return True
        company = self.env.company
        expense = self.env["account.account"].search(
            [
                "|",
                ("code", "=like", "6410%"),
                ("code", "=like", "6300%"),
            ],
            limit=1,
        )
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", company.id)],
            limit=1,
        )
        if not expense or not journal:
            return False
        self.create(
            {
                "name": "Prime score ≥ 80",
                "trigger_type": "score_threshold",
                "trigger_value": 80,
                "calculation_method": "fixed",
                "amount_fixed": 250,
                "frequency": "quarterly",
                "accounting_account_id": expense.id,
                "journal_id": journal.id,
            }
        )
        self.create(
            {
                "name": "Meilleur score département (trimestre)",
                "trigger_type": "period_top",
                "calculation_method": "fixed",
                "amount_fixed": 500,
                "frequency": "quarterly",
                "accounting_account_id": expense.id,
                "journal_id": journal.id,
            }
        )
        return True
