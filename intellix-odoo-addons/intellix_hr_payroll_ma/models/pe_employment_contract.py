# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class PeEmploymentContract(models.Model):
    _inherit = "pe.employment.contract"

    payslip_ma_count = fields.Integer(compute="_compute_payslip_ma_count")

    def _compute_payslip_ma_count(self):
        Payslip = self.env["hr.payslip.ma"]
        for rec in self:
            rec.payslip_ma_count = Payslip.search_count(
                [("contract_id", "=", rec.id)]
            )

    def _is_ma_payroll_eligible(self):
        self.ensure_one()
        company = self.employee_id.company_id
        if not self.env["res.company"]._is_morocco_payroll_company(company):
            return False
        if self.contract_type == "freelance":
            return False
        profile = self.profile_id
        if profile and profile.hors_paie_maroc:
            return False
        if profile and profile.pays_affectation and profile.pays_affectation != "MA":
            return False
        return True

    def action_generate_ma_payslip(self):
        self.ensure_one()
        if not self._is_ma_payroll_eligible():
            raise UserError(
                _("Ce contrat n'est pas éligible à la paie Maroc IntelliX.")
            )
        payslip = self.env["hr.payslip.ma"].create_from_contract(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Bulletin Maroc"),
            "res_model": "hr.payslip.ma",
            "view_mode": "form",
            "res_id": payslip.id,
        }

    def action_view_ma_payslips(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bulletins Maroc"),
            "res_model": "hr.payslip.ma",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id},
        }
