# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PeopleEnginePrimeEngine(models.AbstractModel):
    _name = "pe.prime.engine"
    _description = "Moteur primes People Engine"

    @api.model
    def calculate_prime_for_profile(self, profile, period_start, period_end):
        rules = self.env["pe.prime.rule"].search([("is_active", "=", True)])
        proposed = self.env["pe.prime"]
        for rule in rules:
            amount = self._evaluate_rule(rule, profile, period_start, period_end)
            if amount and amount > 0:
                manager = profile.employee_id.parent_id
                proposed |= self.env["pe.prime"].create(
                    {
                        "profile_id": profile.id,
                        "rule_id": rule.id,
                        "amount_proposed": min(amount, rule.max_amount_per_employee),
                        "period_start": period_start,
                        "period_end": period_end,
                        "trigger_score": profile.score_global,
                        "trigger_details": _(
                            "Score %.1f/100 — %s → %s"
                        )
                        % (profile.score_global, period_start, period_end),
                        "manager_id": manager.id if manager else False,
                        "status": "draft",
                    }
                )
        return proposed

    @api.model
    def _evaluate_rule(self, rule, profile, period_start, period_end):
        if rule.trigger_type == "score_threshold":
            if profile.score_global < (rule.trigger_value or 0):
                return 0
        elif rule.trigger_type == "period_top":
            dept = profile.employee_id.department_id
            if not dept:
                return 0
            others = self.env["pe.employee.profile"].search(
                [
                    ("employee_id.department_id", "=", dept.id),
                    ("id", "!=", profile.id),
                ]
            )
            if any(o.score_global >= profile.score_global for o in others):
                return 0
        elif rule.trigger_type not in ("manual", "score_threshold", "period_top"):
            return 0

        if rule.calculation_method == "fixed":
            return rule.amount_fixed or 0
        if rule.calculation_method == "percent_salary":
            wage = self._get_monthly_wage(profile)
            return wage * (rule.amount_percent or 0) / 100 if wage else 0
        if rule.calculation_method == "tiered":
            try:
                tiers = json.loads(rule.tiered_config or "[]")
            except json.JSONDecodeError:
                tiers = []
            for tier in tiers:
                if tier.get("min", 0) <= profile.score_global <= tier.get("max", 100):
                    return tier.get("amount", 0)
            return 0
        if rule.calculation_method == "per_point":
            return profile.score_global * (rule.amount_fixed or 1)
        return 0

    @api.model
    def _get_monthly_wage(self, profile):
        Contract = self.env.get("hr.contract")
        if not Contract:
            return 0
        contracts = Contract.search(
            [("employee_id", "=", profile.employee_id.id)],
            order="date_start desc",
            limit=1,
        )
        if contracts:
            return getattr(contracts, "wage", 0) or 0
        return 0

    @api.model
    def create_accounting_entry(self, prime):
        prime.ensure_one()
        if not prime.dg_approved:
            raise UserError(_("Approbation DG requise avant écriture comptable."))
        if prime.rule_id.requires_hr and not prime.hr_approved:
            raise UserError(_("Approbation RH requise."))
        if prime.rule_id.requires_manager and not prime.manager_approved:
            raise UserError(_("Approbation gestionnaire requise."))

        rule = prime.rule_id
        amount = prime.dg_amount_override or prime.amount_approved or prime.amount_proposed
        payable = self._get_payable_account()
        if not payable:
            raise UserError(
                _("Compte à payer introuvable (code 2305). Configurez le plan comptable.")
            )

        line_vals = [
            (
                0,
                0,
                {
                    "name": _("Prime performance — %s") % prime.employee_id.name,
                    "account_id": rule.accounting_account_id.id,
                    "debit": amount,
                    "credit": 0,
                },
            ),
            (
                0,
                0,
                {
                    "name": _("Prime à verser — %s") % prime.employee_id.name,
                    "account_id": payable.id,
                    "debit": 0,
                    "credit": amount,
                },
            ),
        ]
        if rule.analytic_account_id:
            line_vals[0][2]["analytic_distribution"] = {
                str(rule.analytic_account_id.id): 100
            }

        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": rule.journal_id.id,
                "date": fields.Date.today(),
                "ref": _("Prime PE — %s") % prime.employee_id.name,
                "line_ids": line_vals,
            }
        )
        prime.write(
            {
                "move_id": move.id,
                "accounting_approved": True,
                "accounting_date": fields.Datetime.now(),
                "amount_approved": amount,
            }
        )
        self._notify_employee_prime_approved(prime)
        return move

    @api.model
    def _get_payable_account(self):
        return self.env["account.account"].search(
            [("code", "=like", "2305%")],
            limit=1,
        )

    @api.model
    def _notify_employee_prime_approved(self, prime):
        partner = prime.profile_id.user_id.partner_id
        if partner:
            prime.profile_id.message_post(
                body=_("Votre prime de performance a été approuvée (montant : %.2f).")
                % (prime.amount_approved or prime.amount_proposed),
                partner_ids=[partner.id],
            )
            prime.write(
                {
                    "employee_notified": True,
                    "employee_notified_date": fields.Datetime.now(),
                }
            )

    @api.model
    def get_prime_budget_status(self, period_start, period_end):
        primes = self.env["pe.prime"].search(
            [
                ("period_start", ">=", period_start),
                ("period_end", "<=", period_end),
                ("status", "not in", ["rejected", "cancelled"]),
            ]
        )
        total = sum(primes.mapped("amount_proposed"))
        limits = self.env["pe.prime.rule"].search([]).mapped("max_total_budget")
        budget_limit = min(limits) if limits else 50000.0
        return {
            "total_proposed": total,
            "budget_limit": budget_limit,
            "remaining": budget_limit - total,
            "over_budget": total > budget_limit,
        }

    @api.model
    def _cron_monthly_prime_calculation(self):
        from datetime import date

        today = date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(day=31)
        else:
            from datetime import timedelta

            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        profiles = self.env["pe.employee.profile"].search(
            [("pe_status", "!=", "inactive"), ("score_global", ">=", 60)]
        )
        for profile in profiles:
            self.calculate_prime_for_profile(profile, start, end)
