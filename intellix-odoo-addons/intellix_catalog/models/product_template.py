# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ix_billing_type = fields.Selection(
        [
            ("one_time", "Setup / ponctuel"),
            ("monthly", "Mensuel"),
            ("usage", "À l'usage"),
            ("quote_only", "Sur devis"),
        ],
        string="Type de facturation",
        default="one_time",
    )
    ix_price_mad = fields.Float(
        string="Prix Digital Doorway (dh)",
        digits="Product Price",
        help="Prix fixe en dirhams — pas de conversion automatique.",
    )
    ix_price_cad = fields.Float(
        string="Prix Agence Doorway ($CAD)",
        digits="Product Price",
        help="Prix fixe en dollars canadiens — pas de conversion automatique.",
    )
    ix_quote_only = fields.Boolean(
        string="Sur devis uniquement",
        help="Affiché au catalogue mais sans prix ferme (personnalisation).",
    )

    def _register_hook(self):
        super()._register_hook()
        from .. import hooks
        try:
            hooks._archive_call_center(self.env)
            hooks._ensure_pricelists(self.env)
        except Exception:
            pass
