# -*- coding: utf-8 -*-
from odoo import models


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    def _get_compatible_providers(
        self,
        company_id,
        partner_id,
        amount,
        currency_id=None,
        force_tokenization=False,
        is_express_checkout=False,
        is_validation=False,
        report=None,
        **kwargs
    ):
        providers = super()._get_compatible_providers(
            company_id,
            partner_id,
            amount,
            currency_id=currency_id,
            force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout,
            is_validation=is_validation,
            report=report,
            **kwargs
        )
        company = self.env["res.company"].browse(company_id)
        currency = (
            self.env["res.currency"].browse(currency_id)
            if currency_id
            else company.currency_id
        )
        name = (company.name or "").lower()
        is_maroc = currency.name == "MAD" or "digital doorway" in name
        is_quebec = currency.name == "CAD" or "agence doorway" in name
        if is_maroc:
            # Maroc : virement RIB uniquement — jamais Stripe.
            return providers.filtered(
                lambda p: (
                    p.code in ("custom", "transfer", "none")
                    and "stripe" not in (p.name or "").lower()
                    and "interac" not in (p.name or "").lower()
                )
            )
        if is_quebec:
            return providers.filtered(
                lambda p: p.code == "stripe"
                or "interac" in (p.name or "").lower()
            )
        return providers
