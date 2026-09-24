# -*- coding: utf-8 -*-
import os


def post_init_hook(env):
    """Crée le tenant principal + charge les clés Stripe depuis l'environnement."""
    icp = env["ir.config_parameter"].sudo()
    mapping = {
        "doorway_credits.stripe_secret_key": "STRIPE_SECRET_KEY",
        "doorway_credits.stripe_publishable_key": "STRIPE_PUBLISHABLE_KEY",
        "doorway_credits.stripe_webhook_secret": "STRIPE_WEBHOOK_SECRET",
        "doorway_credits.stripe_subscription_price_id": "STRIPE_SUBSCRIPTION_PRICE_ID",
        "doorway_credits.trial_credits_amount": "TRIAL_CREDITS_AMOUNT",
    }
    for param, env_key in mapping.items():
        if not icp.get_param(param) and os.environ.get(env_key):
            icp.set_param(param, os.environ[env_key])

    env["doorway.tenant"]._doorway_credits_fix_access()
