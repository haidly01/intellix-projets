# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x_payroll_ma_enabled = fields.Boolean(
        string="Paie Maroc activée",
        help="Active les menus et fonctionnalités de paie Maroc pour cette société.",
    )
    x_payroll_ma_journal_id = fields.Many2one(
        "account.journal",
        string="Journal paie MA",
        domain="[('company_id', '=', id)]",
    )

    @api.model
    def _is_morocco_payroll_company(self, company):
        if not company:
            return False
        return bool(
            company.x_payroll_ma_enabled
            or (company.country_id and company.country_id.code == "MA")
        )

    def _ensure_payroll_ma_accounts(self):
        """Crée ou retrouve les comptes CGNC paie et le journal « Paie MA »."""
        self.ensure_one()
        Account = self.env["account.account"].sudo()
        Journal = self.env["account.journal"].sudo()

        account_defs = [
            ("61711", "Appointements et salaires", "expense"),
            ("61741", "Charges sociales — CNSS/AMO/CIMR", "expense"),
            ("4432", "Rémunérations dues au personnel", "liability_current"),
            ("4433", "Cotisations sociales à payer", "liability_current"),
            ("4452", "État — IR retenu à la source", "liability_current"),
        ]
        accounts = {}
        for code, name, acc_type in account_defs:
            acc = Account.search(
                [
                    ("code", "=", code),
                    ("company_ids", "in", self.id),
                ],
                limit=1,
            )
            if not acc:
                acc = Account.create(
                    {
                        "code": code,
                        "name": name,
                        "account_type": acc_type,
                        "company_ids": [(6, 0, [self.id])],
                    }
                )
            accounts[code] = acc

        journal = self.x_payroll_ma_journal_id
        if not journal:
            journal = Journal.search(
                [
                    ("code", "=", "PAIMA"),
                    ("company_id", "=", self.id),
                ],
                limit=1,
            )
        if not journal:
            journal = Journal.create(
                {
                    "name": "Paie MA",
                    "code": "PAIMA",
                    "type": "general",
                    "company_id": self.id,
                }
            )
            self.sudo().write({"x_payroll_ma_journal_id": journal.id})

        return accounts, journal

    def get_payroll_ma_account(self, code):
        self.ensure_one()
        acc = self.env["account.account"].sudo().search(
            [
                ("code", "=", code),
                ("company_ids", "in", self.id),
            ],
            limit=1,
        )
        if not acc:
            self._ensure_payroll_ma_accounts()
            acc = self.env["account.account"].sudo().search(
                [
                    ("code", "=", code),
                    ("company_ids", "in", self.id),
                ],
                limit=1,
            )
        return acc
