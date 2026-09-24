# -*- coding: utf-8 -*-
{
    "name": "Doorway — Traffic Manager IA",
    "version": "19.0.3.3.0",
    "category": "Marketing",
    "summary": "Campagnes publicitaires IA — analyse marque, audiences, optimisation",
    "description": """
        Traffic Manager IA pour Intellix CRM.
        Questionnaire marque · Campagnes · Audiences · Créatifs · Optimisation · Rapports.
        Toute action IA est soumise à validation humaine avant exécution.
    """,
    "author": "Agence Doorway",
    "depends": [
        "crm",
        "mail",
        "web",
        "intellix_branding",
        "doorway_social_ia",
    ],
    "data": [
        "security/traffic_security.xml",
        "security/ir.model.access.csv",
        "data/brand_tone_tags.xml",
        "data/traffic_channel_data.xml",
        "data/cron_daily_optimization.xml",
        "data/cron_sync_campaigns.xml",
        "data/cron_heygen_creative.xml",
        "data/cron_weekly_report.xml",
        "data/cron_cpa_alerts.xml",
        "data/traffic_config_data.xml",
        "data/bootstrap_campaigns.xml",
        "data/backfill_zones.xml",
        "data/assets.xml",
        "views/campaign_views.xml",
        "views/campaign_optimization_views.xml",
        "views/brand_foundation_views.xml",
        "views/audience_views.xml",
        "views/placement_views.xml",
        "views/creative_views.xml",
        "views/report_views.xml",
        "views/traffic_client_actions.xml",
        "views/menu_items.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_traffic_manager/static/src/xml/traffic_manager.xml",
            "doorway_traffic_manager/static/src/js/traffic_manager.js",
            "doorway_traffic_manager/static/src/css/traffic_manager.css",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
