# -*- coding: utf-8 -*-
from odoo import api, models


class PayrollEngineMa(models.AbstractModel):
    _name = "payroll.engine.ma"
    _description = "Moteur de calcul paie Maroc"

    @api.model
    def compute_payslip(self, payslip):
        employee = payslip.employee_id
        company = payslip.company_id
        gross = payslip.gross_salary or 0.0
        rules = payslip.structure_id.rule_ids.sorted("sequence")

        cnss_ceiling = 6000.0
        cnss_rule = rules.filtered(lambda r: r.code in ("CNSS_EMP", "CNSS_PAT"))[:1]
        if cnss_rule and cnss_rule.ceiling:
            cnss_ceiling = cnss_rule.ceiling
        cnss_base = min(gross, cnss_ceiling) if cnss_ceiling else gross

        lines = []
        total_deductions = 0.0
        total_employer = 0.0

        for rule in rules:
            amount = employer = base = 0.0
            rate = rule.rate

            if rule.code == "BASIC":
                base = gross
                amount = gross
            elif rule.computation_type == "ir_ma":
                base = gross
                amount = self._compute_ir_monthly(employee, gross, company)
            elif rule.computation_type == "fixed":
                base = gross
                amount = rule.fixed_amount
            elif rule.computation_type == "percentage":
                base = self._get_base_amount(rule, gross, cnss_base, employee)
                if base <= 0:
                    continue
                if rule.category == "charge_patronale":
                    pat_rate = rule.employer_rate or rule.rate
                    if rule.code == "CIMR_PAT":
                        pat_rate = (
                            employee.x_cimr_employer_rate or employee.x_cimr_rate or 0.0
                        )
                        if not pat_rate:
                            continue
                        rate = pat_rate
                    employer = round(base * pat_rate / 100.0, 2)
                elif rule.code == "CIMR_EMP":
                    emp_rate = employee.x_cimr_rate or 0.0
                    if not emp_rate:
                        continue
                    rate = emp_rate
                    amount = round(base * emp_rate / 100.0, 2)
                else:
                    amount = round(base * rule.rate / 100.0, 2)
                    if rule.employer_rate and rule.category == "retenue_salariale":
                        employer = round(base * rule.employer_rate / 100.0, 2)
            else:
                continue

            if amount == 0 and employer == 0:
                continue

            lines.append(self._line_vals(rule, amount, employer, base, rate))
            total_deductions += amount if rule.category == "retenue_salariale" else 0.0
            total_employer += employer

        net = round(gross - total_deductions, 2)
        lines.append(
            {
                "rule_id": False,
                "sequence": 999,
                "code": "NET",
                "name": "Net à payer",
                "category": "info",
                "amount": net,
                "employer_amount": round(total_employer, 2),
                "base_amount": gross,
                "rate": 0.0,
                "appears_on_payslip": True,
            }
        )
        return {"lines": lines, "net_salary": net}

    @api.model
    def _line_vals(self, rule, amount, employer_amount, base, rate):
        return {
            "rule_id": rule.id,
            "sequence": rule.sequence,
            "code": rule.code,
            "name": rule.name,
            "category": rule.category,
            "amount": amount,
            "employer_amount": employer_amount,
            "base_amount": base,
            "rate": rate,
            "appears_on_payslip": rule.appears_on_payslip,
        }

    @api.model
    def _get_base_amount(self, rule, gross, cnss_base, employee):
        if rule.base_type == "cnss_capped":
            return cnss_base
        if rule.base_type == "gross_if_cimr":
            return gross if employee.x_cimr_rate else 0.0
        return gross

    @api.model
    def _compute_ir_monthly(self, employee, monthly_gross, company):
        config = self.env["hr.ir.config"].search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
        if not config:
            config = self.env["hr.ir.config"].create({"company_id": company.id})

        annual_gross = monthly_gross * 12.0
        frais_pro = min(
            annual_gross * config.professional_expense_rate / 100.0,
            config.professional_expense_annual_cap,
        )
        net_imposable = max(annual_gross - frais_pro, 0.0)
        ir_annual = self._apply_brackets(net_imposable, company)

        dependents = min(employee.children or 0, config.max_dependents)
        if config.include_spouse and employee.marital in ("married", "cohabitant"):
            dependents += 1
        family_ded = dependents * config.family_deduction_annual
        ir_net_annual = max(ir_annual - family_ded, 0.0)
        return round(ir_net_annual / 12.0, 2)

    @api.model
    def _apply_brackets(self, taxable_annual, company):
        brackets = self.env["hr.ir.bracket"].search(
            [("company_id", "=", company.id), ("active", "=", True)],
            order="min_amount asc",
        )
        if not brackets or taxable_annual <= 0:
            return 0.0

        tax = 0.0
        for bracket in brackets:
            lower = bracket.min_amount
            upper = bracket.max_amount or taxable_annual
            if taxable_annual <= lower:
                continue
            taxable_in_band = min(taxable_annual, upper) - lower
            if taxable_in_band > 0:
                tax += taxable_in_band * bracket.rate / 100.0
        return tax
