# -*- coding: utf-8 -*-
{
    "name": "Doorway Crédits IA & Stripe SaaS",
    "version": "19.0.2.1.0",
    "category": "Sales",
    "summary": "Multi-tenant crédits IA, abonnements 89$/user, packs Stripe",
    "description": """
        Plateforme SaaS Doorway : comptes crédits, débit services IA,
        abonnements Stripe et packs prépayés.
    """,
    "author": "Agence Doorway",
    "depends": ["base", "mail", "base_setup", "intellix_branding", "doorway_agents_dashboard", "doorway_onboarding"],
    "external_dependencies": {"python": ["stripe"]},
    "data": [
        "security/doorway_credits_security.xml",
        "security/ir.model.access.csv",
        "data/credits_access_fix.xml",
        "data/onboarding.xml",
        "data/pricing_data.xml",
        "data/sofia_es_pricing_data.xml",
        "data/credit_packs_data.xml",
        "views/credit_pack_views.xml",
        "views/credit_purchase_views.xml",
        "views/subscription_views.xml",
        "views/dashboard_tenant.xml",
        "views/dashboard_admin.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
