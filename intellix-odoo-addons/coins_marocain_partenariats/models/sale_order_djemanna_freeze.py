# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _coins_sync_entente_from_quote(self):
        """Ne jamais réécrire les clauses de S00021 / Riad Djemanna."""
        frozen = self.filtered(
            lambda order: (order.name or "") == "S00021"
            or "djemanna" in (
                (order.origin or "")
                + " "
                + (order.client_order_ref or "")
                + " "
                + (order.partner_id.name or "")
            ).lower()
        )
        return super(SaleOrder, self - frozen)._coins_sync_entente_from_quote()
