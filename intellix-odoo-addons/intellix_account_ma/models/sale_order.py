# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _intellix_apply_billing_company(self, partner, current_company=None):
        if not partner:
            return
        target = self.env["res.company"].intellix_resolve_sales_company(
            partner, current_company
        )
        return target

    @api.onchange("partner_id")
    def _onchange_partner_intellix_company(self):
        for order in self:
            if not order.partner_id:
                continue
            target = order._intellix_apply_billing_company(
                order.partner_id, order.company_id
            )
            if target and target != order.company_id:
                order.company_id = target

    @api.model_create_multi
    def create(self, vals_list):
        ResCompany = self.env["res.company"]
        for vals in vals_list:
            partner_id = vals.get("partner_id")
            if not partner_id:
                continue
            partner = self.env["res.partner"].browse(partner_id)
            target = ResCompany.intellix_resolve_sales_company(
                partner,
                ResCompany.browse(vals.get("company_id")) if vals.get("company_id") else None,
            )
            if target:
                vals["company_id"] = target.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("partner_id"):
            partner = self.env["res.partner"].browse(vals["partner_id"])
            target = self.env["res.company"].intellix_resolve_sales_company(partner)
            if target:
                vals["company_id"] = target.id
        return super().write(vals)

    def _prepare_invoice(self):
        self.ensure_one()
        vals = super()._prepare_invoice()
        target = self.env["res.company"].intellix_resolve_sales_company(
            self.partner_id, self.company_id
        )
        if target:
            vals["company_id"] = target.id
        return vals
