# -*- coding: utf-8 -*-
{
    "name": "Réno Immobilier",
    "version": "19.0.1.2.8",
    "category": "Sales/CRM",
    "summary": "Application Réno Immobilier — Leads Gestion et partenaires",
    "description": """
Application séparée Réno Immobilier (hors renovation_conciergerie).

Cinq colonnes Leads Gestion :
Nouveau, Contacté, Attribué, Relance, Gagné (Perdu replié).

RénoFacile est filtré (pause), jamais supprimé.
""",
    "author": "IntelliX / Agence Doorway",
    "depends": [
        "web",
        "crm",
        "sales_team",
        "renovation_conciergerie",
        "coins_marocain_partenariats",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/crm_team_stages.xml",
        "data/app_menu_order.xml",
        "views/crm_lead_views.xml",
        "views/partner_package_views.xml",
        "views/reno_partner_views.xml",
        "views/dashboard_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "reno_immobilier/static/src/css/reno_pipeline.css",
            "reno_immobilier/static/src/css/reno_dashboard.css",
            "reno_immobilier/static/src/css/reno_lead_form.css",
            "reno_immobilier/static/src/xml/reno_dashboard.xml",
            "reno_immobilier/static/src/js/reno_pipeline_theme.js",
            "reno_immobilier/static/src/js/reno_lead_form.js",
            "reno_immobilier/static/src/js/reno_dashboard.js",
        ],
        "web.assets_web_dark": [
            "reno_immobilier/static/src/css/reno_pipeline.css",
            "reno_immobilier/static/src/css/reno_dashboard.css",
            "reno_immobilier/static/src/css/reno_lead_form.css",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
