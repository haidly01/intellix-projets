# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from odoo.addons.intellix_account_ma.services.ma_account_setup import (
    PAYROLL_CODE_ALIASES,
    configure_moroccan_company,
)

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    x_intellix_accounting_region = fields.Selection(
        [
            ("ma", "Maroc (CGNC)"),
            ("ca", "Canada"),
        ],
        string="Région comptable IntelliX",
        help="Détermine le plan comptable et le routage des ventes IntelliX.",
    )

    @api.model
    def _intellix_company_for_region(self, region):
        """Retourne la société IntelliX pour une région comptable (ma / ca)."""
        company = self.search(
            [("x_intellix_accounting_region", "=", region)],
            order="id",
            limit=1,
        )
        if company:
            return company
        if region == "ma":
            main = self.env.ref("base.main_company", raise_if_not_found=False)
            ma = self.env.ref("base.ma", raise_if_not_found=False)
            if main and ma and main.partner_id.country_id == ma:
                return main
            if ma:
                return self.search(
                    [("partner_id.country_id", "=", ma.id)], order="id", limit=1
                )
        if region == "ca":
            ca = self.env.ref("base.ca", raise_if_not_found=False)
            if ca:
                return self.search(
                    [("partner_id.country_id", "=", ca.id)], order="id", limit=1
                )
        return self.browse()

    @api.model
    def _intellix_ma_company(self):
        return self._intellix_company_for_region("ma")

    @api.model
    def _intellix_ca_company(self):
        return self._intellix_company_for_region("ca")

    @api.model
    def intellix_resolve_sales_company(self, partner, current_company=None):
        """Route un devis/facture vers la société MA ou CA selon le client."""
        ma = self._intellix_ma_company()
        ca = self._intellix_ca_company()
        current = current_company or self.env.company

        if not partner:
            return current

        if partner.x_billing_company_id:
            return partner.x_billing_company_id

        country = partner.country_id.code if partner.country_id else False

        if country == "CA" and ca:
            return ca

        if country == "MA" and ma:
            return ma

        if partner.company_id and partner.company_id.x_intellix_accounting_region in ("ma", "ca"):
            return partner.company_id

        if current.x_intellix_accounting_region == "ca" or current.country_code == "CA":
            return ca or current

        # Export / hors Maroc : comptabilité marocaine (TVA 0 % export services)
        if ma:
            return ma

        return current

    def get_payroll_ma_account(self, code):
        """Étend la recherche paie aux codes CGNC 6 chiffres."""
        self.ensure_one()
        Account = self.env["account.account"].sudo()
        candidates = PAYROLL_CODE_ALIASES.get(code, [code])
        for candidate in candidates:
            acc = Account.search(
                [("code", "=", candidate), ("company_ids", "in", self.id)],
                limit=1,
            )
            if acc:
                return acc
        if hasattr(super(), "get_payroll_ma_account"):
            return super().get_payroll_ma_account(code)
        configure_moroccan_company(self.env, self)
        for candidate in candidates:
            acc = Account.search(
                [("code", "=", candidate), ("company_ids", "in", self.id)],
                limit=1,
            )
            if acc:
                return acc
        return Account

    def action_intellix_reload_ma_chart(self):
        """Action manuelle : recharger / compléter le plan CGNC."""
        for company in self:
            configure_moroccan_company(self.env, company)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            code = company.country_code
            if code == "MA" and not company.x_intellix_accounting_region:
                company.x_intellix_accounting_region = "ma"
            elif code == "CA" and not company.x_intellix_accounting_region:
                company.x_intellix_accounting_region = "ca"
        return companies
