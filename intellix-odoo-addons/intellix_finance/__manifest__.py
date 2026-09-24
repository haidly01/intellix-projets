# -*- coding: utf-8 -*-
{
    "name": "Finance",
    "version": "19.0.1.8.1",
    "category": "Sales/CRM",
    "summary": "ITEX, Driven et Growth Capital — pré-qualification et entonnoir de financement",
    "description": """
Module Finance IntelliX.

Trois sections de marque : ITEX (troc / réseau), Driven et Growth Capital
(financement B2B fonds de roulement). Driven et Growth Capital partagent
les mêmes critères et le même entonnoir à 7 étapes, mais jamais les
métriques agrégées.

Le dashboard partenaires ITEX existant (coins_marocain_partenariats)
est réutilisé comme section — il n'est pas recopié.
""",
    "author": "IntelliX / Agence Doorway",
    "depends": [
        "base",
        "crm",
        "web",
        "renovation_conciergerie",
        "coins_marocain_partenariats",
        "payment",
        "mail",
        "sms",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/finance_teams.xml",
        "data/itex_funnel_stages.xml",
        "data/itex_exchange_services.xml",
        "data/itex_config.xml",
        "data/itex_mail_templates.xml",
        "data/itex_cron.xml",
        "views/crm_lead_finance_views.xml",
        "views/crm_lead_itex_views.xml",
        "views/finance_dashboard_views.xml",
        "views/itex_portal_dashboard.xml",
        "views/finance_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "intellix_finance/static/src/css/finance_pipeline_kanban.css",
            "intellix_finance/static/src/css/finance_dashboard.css",
            "intellix_finance/static/src/xml/finance_dashboard.xml",
            "intellix_finance/static/src/xml/itex_dashboard_funnel.xml",
            "intellix_finance/static/src/js/finance_dashboard.js",
            "intellix_finance/static/src/xml/driven_dashboard.xml",
            "intellix_finance/static/src/js/driven_dashboard.js",
        ],
        "web.assets_web_dark": [
            "intellix_finance/static/src/css/finance_pipeline_kanban.css",
            "intellix_finance/static/src/css/finance_dashboard.css",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "sequence": 6,
    "license": "LGPL-3",
}
