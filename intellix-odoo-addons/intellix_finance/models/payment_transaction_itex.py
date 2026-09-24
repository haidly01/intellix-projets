# -*- coding: utf-8 -*-
from odoo import api, fields, models

ITEX_PAID_TX_STATES = ("done", "authorized")


class PaymentTransactionItex(models.Model):
    _inherit = "payment.transaction"

    itex_initial_lead_id = fields.Many2one(
        "crm.lead",
        string="Lead ITEX (adhésion)",
        ondelete="set null",
        index=True,
    )
    itex_monthly_lead_id = fields.Many2one(
        "crm.lead",
        string="Lead ITEX (mensualité)",
        ondelete="set null",
        index=True,
    )

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            self._itex_sync_lead_payment()
        return res

    def _itex_sync_lead_payment(self):
        for tx in self:
            if tx.state not in ITEX_PAID_TX_STATES:
                continue
            if tx.itex_initial_lead_id:
                tx.itex_initial_lead_id._itex_on_initial_payment_confirmed()
            if tx.itex_monthly_lead_id:
                tx.itex_monthly_lead_id._itex_on_monthly_payment_confirmed()
