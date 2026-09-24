# -*- coding: utf-8 -*-
from odoo import api, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.model
    def _intellix_activate_outstanding_payment_accounts(self):
        """Réactive les comptes transitoires requis pour enregistrer un paiement."""
        chart = self.env['account.chart.template']
        PaymentLine = self.env['account.payment.method.line']
        configs = (
            ('inbound', 'account_journal_payment_debit_account_id'),
            ('outbound', 'account_journal_payment_credit_account_id'),
        )
        for company in self.env['res.company'].search([]):
            for payment_type, xml_ref in configs:
                account = chart.with_company(company).ref(xml_ref, raise_if_not_found=False)
                if not account:
                    continue
                if not account.active:
                    account.active = True
                lines = PaymentLine.search([
                    ('company_id', '=', company.id),
                    ('journal_id.type', 'in', ('bank', 'cash', 'credit')),
                    ('payment_type', '=', payment_type),
                    '|',
                    ('payment_account_id', '=', False),
                    ('payment_account_id', '=', account.id),
                ])
                lines.write({'payment_account_id': account.id})
