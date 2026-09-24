# -*- coding: utf-8 -*-
from odoo import _, fields, models


class DoorwayCreditPack(models.Model):
    _name = "doorway.credit.pack"
    _description = "Pack de crédits prépayés"
    _order = "price_usd"

    name = fields.Char(required=True)
    price_usd = fields.Float(string="Prix USD", required=True)
    credits_amount = fields.Float(string="Crédits accordés (USD)", required=True)
    bonus_percent = fields.Float(string="Bonus %", default=0.0)
    stripe_price_id = fields.Char(string="Stripe Price ID")
    is_active = fields.Boolean(default=True)
    description = fields.Text()

    def action_buy_pack(self):
        """Ouvre le paywall pré-rempli avec ce pack (choix du mode de paiement)."""
        self.ensure_one()
        wizard = self.env["doorway.credit.paywall"].create(
            {
                "company_id": self.env.company.id,
                "pack_id": self.id,
                "balance_credits": self.env["doorway.credit.api"].get_balance(self.env.company),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Acheter %s") % self.name,
            "res_model": "doorway.credit.paywall",
            "view_mode": "form",
            "target": "new",
            "res_id": wizard.id,
        }
