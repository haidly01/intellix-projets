# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _intellix_apply_customer_company(self, vals):
        if vals.get("move_type") not in ("out_invoice", "out_refund", "out_receipt"):
            return
        partner_id = vals.get("partner_id")
        if not partner_id:
            return
        partner = self.env["res.partner"].browse(partner_id)
        target = self.env["res.company"].intellix_resolve_sales_company(
            partner,
            self.env["res.company"].browse(vals.get("company_id"))
            if vals.get("company_id")
            else None,
        )
        if target:
            vals["company_id"] = target.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._intellix_apply_customer_company(vals)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("partner_id"):
            partner = self.env["res.partner"].browse(vals["partner_id"])
            if self.filtered(
                lambda m: m.state == "draft"
                and m.move_type in ("out_invoice", "out_refund", "out_receipt")
            ):
                target = self.env["res.company"].intellix_resolve_sales_company(partner)
                if target:
                    vals["company_id"] = target.id
        return super().write(vals)

    @api.constrains("company_id", "journal_id", "line_ids")
    def _check_intellix_company_accounts(self):
        for move in self:
            if move.journal_id.company_id and move.journal_id.company_id != move.company_id:
                raise ValidationError(
                    _(
                        "Le journal « %(journal)s » appartient à %(journal_company)s "
                        "mais la facture est sur %(move_company)s. "
                        "Vérifiez le routage société (Maroc / Canada).",
                        journal=move.journal_id.display_name,
                        journal_company=move.journal_id.company_id.display_name,
                        move_company=move.company_id.display_name,
                    )
                )
            for line in move.line_ids:
                if not line.account_id:
                    continue
                if move.company_id not in line.account_id.company_ids:
                    raise ValidationError(
                        _(
                            "Le compte « %(account)s » n'appartient pas à la société "
                            "« %(company)s ». Impossible de comptabiliser une facture "
                            "Maroc sur le plan Canada (ou inversement).",
                            account=line.account_id.display_name,
                            company=move.company_id.display_name,
                        )
                    )
