# -*- coding: utf-8 -*-
import os

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doorway_stripe_secret_key = fields.Char(config_parameter="doorway_credits.stripe_secret_key")
    doorway_stripe_publishable_key = fields.Char(
        config_parameter="doorway_credits.stripe_publishable_key"
    )
    doorway_stripe_webhook_secret = fields.Char(
        config_parameter="doorway_credits.stripe_webhook_secret"
    )
    doorway_stripe_subscription_price_id = fields.Char(
        config_parameter="doorway_credits.stripe_subscription_price_id"
    )
    doorway_trial_credits = fields.Float(
        default=25.0, config_parameter="doorway_credits.trial_credits_amount"
    )

    # --- Paywall : coûts par action (en crédits) ---
    doorway_cost_site_publish = fields.Float(
        string="Coût publication site (crédits)",
        default=1.0,
        config_parameter="doorway_credits.cost_site_publish",
    )
    doorway_cost_email_send = fields.Float(
        string="Coût envoi mailing (crédits)",
        default=1.0,
        config_parameter="doorway_credits.cost_email_send",
    )
    doorway_cost_seo_publish = fields.Float(
        string="Coût application SEO en ligne (crédits)",
        default=1.0,
        config_parameter="doorway_credits.cost_seo_publish",
    )
    doorway_cost_social_publish = fields.Float(
        string="Coût publication réseau social (crédits)",
        default=1.0,
        config_parameter="doorway_credits.cost_social_publish",
    )

    # --- Paiements hors-ligne (manuels) ---
    doorway_interac_email = fields.Char(
        string="Email Interac (destinataire)",
        config_parameter="doorway_credits.interac_email",
    )
    doorway_rib_iban = fields.Char(
        string="IBAN / RIB", config_parameter="doorway_credits.rib_iban"
    )
    doorway_rib_bic = fields.Char(
        string="BIC / SWIFT", config_parameter="doorway_credits.rib_bic"
    )
    doorway_rib_beneficiary = fields.Char(
        string="Bénéficiaire du virement",
        config_parameter="doorway_credits.rib_beneficiary",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env["ir.config_parameter"].sudo()
        env_map = {
            "doorway_stripe_secret_key": "STRIPE_SECRET_KEY",
            "doorway_stripe_publishable_key": "STRIPE_PUBLISHABLE_KEY",
            "doorway_stripe_webhook_secret": "STRIPE_WEBHOOK_SECRET",
            "doorway_stripe_subscription_price_id": "STRIPE_SUBSCRIPTION_PRICE_ID",
        }
        for field_name, env_key in env_map.items():
            if not res.get(field_name):
                res[field_name] = icp.get_param(
                    "doorway_credits.%s" % field_name.replace("doorway_", "")
                ) or os.environ.get(env_key) or ""
        return res
