# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class GeneratePayslipWizard(models.TransientModel):
    _name = "generate.payslip.ma.wizard"
    _description = "Générer bulletin Maroc"

    contract_id = fields.Many2one("pe.employment.contract", string="Contrat")
    employee_id = fields.Many2one("hr.employee", string="Employé")
    period_start = fields.Date(string="Début période")
    period_end = fields.Date(string="Fin période")
    gross_salary = fields.Float(string="Salaire brut")

    def action_generate(self):
        self.ensure_one()
        contract = self.contract_id
        if contract:
            payslip = self.env["hr.payslip.ma"].create_from_contract(
                contract,
                period_start=self.period_start,
                period_end=self.period_end,
            )
            if self.gross_salary:
                payslip.gross_salary = self.gross_salary
                payslip.action_compute()
        elif self.employee_id:
            company = self.employee_id.company_id
            if not self.env["res.company"]._is_morocco_payroll_company(company):
                raise UserError(_("Employé hors société Maroc."))
            structure = self.env["hr.payroll.structure.ma"].search(
                [("company_id", "=", company.id), ("active", "=", True)],
                limit=1,
            )
            if not structure:
                raise UserError(_("Aucune structure de paie pour %s.") % company.name)
            payslip = self.env["hr.payslip.ma"].create(
                {
                    "employee_id": self.employee_id.id,
                    "company_id": company.id,
                    "structure_id": structure.id,
                    "period_start": self.period_start,
                    "period_end": self.period_end,
                    "gross_salary": self.gross_salary,
                }
            )
            payslip.action_compute()
        else:
            raise UserError(_("Sélectionnez un contrat ou un employé."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Bulletin Maroc"),
            "res_model": "hr.payslip.ma",
            "view_mode": "form",
            "res_id": payslip.id,
        }
