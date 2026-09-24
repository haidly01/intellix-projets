# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends(
        'can_edit_wizard',
        'source_amount',
        'source_amount_currency',
        'source_currency_id',
        'company_id',
        'currency_id',
        'payment_date',
        'installments_mode',
        'journal_id',
        'line_ids',
    )
    def _compute_amount(self):
        """Montant par défaut = solde total de la facture ; saisie libre conservée."""
        for wizard in self:
            if wizard.custom_user_amount:
                wizard.amount = wizard.amount
                continue

            total_amount_values = (
                wizard._get_total_amounts_to_pay(wizard.batches)
                if wizard.batches
                else {}
            )
            full_amount = total_amount_values.get('full_amount', 0.0)

            if wizard.journal_id and wizard.currency_id and wizard.payment_date:
                wizard.amount = full_amount
                continue

            # Avant que journal / devise paiement soient calculés : residual facture
            if wizard.source_amount_currency and wizard.source_currency_id:
                wizard.amount = wizard.source_amount_currency
            elif wizard.source_amount:
                wizard.amount = wizard.source_amount
            elif full_amount:
                wizard.amount = full_amount
            else:
                wizard.amount = wizard.amount

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for wizard in records:
            if wizard.custom_user_amount:
                continue
            if wizard.amount:
                continue
            if wizard.source_amount_currency:
                wizard.amount = wizard.source_amount_currency
            elif wizard.source_amount:
                wizard.amount = wizard.source_amount
        return records
