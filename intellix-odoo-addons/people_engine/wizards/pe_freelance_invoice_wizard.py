# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeFreelanceInvoiceWizard(models.TransientModel):
    _name = "pe.freelance.invoice.wizard"
    _description = "Génération factures freelance par période"

    period_start = fields.Date(string="Début période", required=True)
    period_end = fields.Date(string="Fin période", required=True)
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Freelances",
        help="Laisser vide pour tous les contrats freelance actifs.",
    )
    auto_issue = fields.Boolean(
        string="Émettre automatiquement",
        help="Passe les factures calculées au statut Émise.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        period = self.env["pe.payroll.service"].sudo().get_payroll_period()
        res.setdefault("period_start", period["period_start"])
        res.setdefault("period_end", period["period_end"])
        return res

    def action_generate(self):
        self.ensure_one()
        Contract = self.env["pe.employment.contract"].sudo()
        Invoice = self.env["pe.freelance.invoice"].sudo()
        domain = [
            ("contract_type", "=", "freelance"),
            ("statut", "=", "active"),
            ("date_start", "<=", self.period_end),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", self.period_start),
        ]
        if self.employee_ids:
            domain.append(("employee_id", "in", self.employee_ids.ids))
        contracts = Contract.search(domain)
        created = Invoice
        for contract in contracts:
            invoice = Invoice.search(
                [
                    ("employee_id", "=", contract.employee_id.id),
                    ("period_start", "=", self.period_start),
                    ("period_end", "=", self.period_end),
                ],
                limit=1,
            )
            if not invoice:
                invoice = Invoice.create(
                    {
                        "employee_id": contract.employee_id.id,
                        "contrat_id": contract.id,
                        "period_start": self.period_start,
                        "period_end": self.period_end,
                    }
                )
            invoice.action_calculate()
            if self.auto_issue and not invoice.alerte_forfait:
                invoice.action_issue()
            created |= invoice
        return {
            "type": "ir.actions.act_window",
            "name": "Factures freelance générées",
            "res_model": "pe.freelance.invoice",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }
