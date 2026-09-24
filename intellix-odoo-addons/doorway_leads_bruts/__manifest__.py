# -*- coding: utf-8 -*-
{
    "name": "IntelliX Extracteur",
    "version": "19.0.3.1.0",
    "category": "Sales/CRM",
    "summary": "Extraction automatique de leads B2B multi-sources avec crédits IA",
    "description": """
        Génération de leads B2B : mot-clé + région → estimation coût crédits
        → validation → extraction en arrière-plan → qualification CRM.
    """,
    "author": "Agence Doorway",
    "depends": [
        "base",
        "mail",
        "crm",
        "web",
        "intellix_branding",
        "doorway_credits",
        "renovation_conciergerie",
    ],
    "external_dependencies": {
        "python": ["requests", "beautifulsoup4", "lxml"],
    },
    "data": [
        "security/doorway_leads_bruts_security.xml",
        "security/ir.model.access.csv",
        "data/credit_config_data.xml",
        "data/source_registry_data.xml",
        "data/source_registry_tunisie_data.xml",
        "data/source_registry_configurateur_data.xml",
        "data/marketing_assignee_fix.xml",
        "views/credit_views.xml",
        "views/leads_bruts_views.xml",
        "views/campagne_views.xml",
        "wizard/wizard_extraction_views.xml",
        "views/extracteur_hub_views.xml",
        "views/extracteur_campaign_views.xml",
        "views/res_config_settings_views.xml",
        "views/ia_campaign_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_leads_bruts/static/src/css/leads_bruts.css",
            "doorway_leads_bruts/static/src/css/extracteur_configurateur.css",
            "doorway_leads_bruts/static/src/xml/extracteur_hub.xml",
            "doorway_leads_bruts/static/src/xml/extracteur_configurateur.xml",
            "doorway_leads_bruts/static/src/js/extracteur_hub.js",
            "doorway_leads_bruts/static/src/js/extracteur_configurateur.js",
            "doorway_leads_bruts/static/src/js/leads_bruts.js",
            "doorway_leads_bruts/static/src/js/extraction_wizard.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
