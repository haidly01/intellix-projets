# -*- coding: utf-8 -*-
from odoo import fields, models

DOORWAY_VAT = "799456165RT0001"
DOORWAY_INVOICE_START = "1100"


class AccountMove(models.Model):
    _inherit = "account.move"

    def _coins_is_morocco_invoice(self):
        self.ensure_one()
        name = (self.company_id.name or "").lower()
        return self.currency_id.name == "MAD" or "digital doorway" in name

    def _coins_is_doorway_customer_invoice(self):
        """Agence Doorway Inc. (Canada) : factures clients 1102, 1103, …"""
        self.ensure_one()
        vat = (self.company_id.vat or "").replace(" ", "")
        return self.move_type == "out_invoice" and vat == DOORWAY_VAT

    def _get_starting_sequence(self):
        """Digital Doorway : DD-2026-0831 — Agence Doorway : 1102, 1103, …"""
        self.ensure_one()
        if self._coins_is_doorway_customer_invoice():
            return DOORWAY_INVOICE_START
        if self.move_type == "out_invoice" and self._coins_is_morocco_invoice():
            date = self.invoice_date or self.date or fields.Date.context_today(self)
            return "DD-%s-0000" % date.strftime("%Y")
        return super()._get_starting_sequence()

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        """Ne pas enchaîner sur INV/2026/00001 : la série Doorway est 1102+."""
        if self._coins_is_doorway_customer_invoice() and with_prefix is None:
            last = super()._get_last_sequence(relaxed=relaxed, with_prefix="")
            if last and str(last).isdigit():
                return last
            return None
        return super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)

    def _has_to_be_paid(self):
        """Maroc : pas de checkout (RIB sur la facture). Québec : Stripe / Interac."""
        self.ensure_one()
        if self._coins_is_morocco_invoice():
            return False
        return super()._has_to_be_paid()

    def _get_online_payment_error(self):
        self.ensure_one()
        if self._coins_is_morocco_invoice():
            return False
        return super()._get_online_payment_error()
