# -*- coding: utf-8 -*-
from odoo import api, models

INTELLIX_INBOUND_CODES = ('ix_card', 'ix_interac', 'ix_transfer', 'ix_cash')


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        info = super()._get_payment_method_information()
        multi_bank = {'mode': 'multi', 'type': ('bank', 'cash', 'credit')}
        info.update({
            'ix_card': multi_bank,
            'ix_interac': multi_bank,
            'ix_transfer': multi_bank,
            'ix_cash': multi_bank,
        })
        return info

    @api.model
    def _intellix_sync_payment_method_lines(self):
        """Assure les lignes de mode de paiement sur tous les journaux banque/caisse."""
        methods = self.search([
            ('code', 'in', INTELLIX_INBOUND_CODES),
            ('payment_type', '=', 'inbound'),
        ])
        PaymentLine = self.env['account.payment.method.line']
        for method in methods:
            journals = self.env['account.journal'].search(
                method._get_payment_method_domain(method.code)
            )
            existing_journal_ids = PaymentLine.search([
                ('payment_method_id', '=', method.id),
                ('journal_id', 'in', journals.ids),
            ]).mapped('journal_id').ids
            for journal in journals.filtered(lambda j: j.id not in existing_journal_ids):
                PaymentLine.create({
                    'name': method.name,
                    'payment_method_id': method.id,
                    'journal_id': journal.id,
                })
