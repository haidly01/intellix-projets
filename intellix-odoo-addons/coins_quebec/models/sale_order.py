# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .product_template import (
    SETUP_500_CODE,
    SETUP_BOUTIQUE_CODE,
    SPLIT_MAP,
)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    cq_partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        string="Partenariat Coins Québec",
        ondelete="set null",
        copy=False,
        index=True,
    )

    def action_confirm(self):
        self._cq_dedupe_startup_fees()
        res = super().action_confirm()
        self._cq_mark_startup_fee_on_partenariat()
        return res

    def _cq_dedupe_startup_fees(self):
        """Jamais 500$ + 1000$ sur le même devis : le 1000$ remplace le 500$."""
        for order in self:
            lines = order.order_line.filtered(
                lambda l: l.product_id.default_code
                in (SETUP_500_CODE, SETUP_BOUTIQUE_CODE)
            )
            codes = set(lines.mapped("product_id.default_code"))
            if SETUP_500_CODE in codes and SETUP_BOUTIQUE_CODE in codes:
                lines.filtered(
                    lambda l: l.product_id.default_code == SETUP_500_CODE
                ).unlink()

    def _cq_mark_startup_fee_on_partenariat(self):
        for order in self:
            part = order.cq_partenariat_id
            if not part:
                continue
            codes = set(order.order_line.mapped("product_id.default_code"))
            if SETUP_BOUTIQUE_CODE in codes:
                part.sudo().write(
                    {
                        "mon_coin_startup_fee_kind": "boutique_1000",
                        "mon_coin_startup_fee_invoiced": True,
                    }
                )
            elif SETUP_500_CODE in codes:
                part.sudo().write(
                    {
                        "mon_coin_startup_fee_kind": "clover_500",
                        "mon_coin_startup_fee_invoiced": True,
                    }
                )


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    mon_coin_pay_kind = fields.Selection(
        [
            ("itex", "Part ITEX"),
            ("cash", "Part argent"),
            ("either", "ITEX ou argent"),
        ],
        string="Règlement Mon Coin",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if self.env.context.get("cq_skip_mon_coin_split"):
            return lines
        lines._cq_expand_itex_split()
        return lines

    def _cq_expand_itex_split(self):
        """Mesure / Complet → 2 lignes (ITEX 50$ + part argent). Pas de faux bouton."""
        Product = self.env["product.product"].sudo()
        for line in self:
            code = line.product_id.default_code
            parts = SPLIT_MAP.get(code)
            if not parts:
                continue
            order = line.order_id
            existing = set(order.order_line.mapped("product_id.default_code"))
            itex = Product.search([("default_code", "=", parts[0])], limit=1)
            cash = Product.search([("default_code", "=", parts[1])], limit=1)
            if not itex or not cash:
                continue
            to_create = []
            if parts[0] not in existing:
                to_create.append(
                    {
                        "order_id": order.id,
                        "product_id": itex.id,
                        "product_uom_qty": line.product_uom_qty or 1.0,
                        "mon_coin_pay_kind": "itex",
                    }
                )
            if parts[1] not in existing:
                to_create.append(
                    {
                        "order_id": order.id,
                        "product_id": cash.id,
                        "product_uom_qty": line.product_uom_qty or 1.0,
                        "mon_coin_pay_kind": "cash",
                    }
                )
            if to_create:
                self.with_context(cq_skip_mon_coin_split=True).create(to_create)
            # Le produit catalogue (150$ / 250$) reste visible ; qty 0 évite
            # de facturer 3 fois. Les 2 lignes split portent le montant réel.
            if line.product_uom_qty:
                line.with_context(cq_skip_mon_coin_split=True).write(
                    {"product_uom_qty": 0.0, "name": _("%s — éclaté ITEX + argent") % line.name}
                )
