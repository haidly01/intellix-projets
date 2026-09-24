# -*- coding: utf-8 -*-
{
    'name': 'Doorway — Veille Sociale & Gestion Communauté',
    'version': '19.0.1.12.0',
    'category': 'Marketing',
    'summary': 'Tableau de bord veille rénovation + planification communauté + leads CRM',
    'description': """
        Module de veille sociale pour Agence Doorway.
        - Sync automatique depuis Supabase (table veille_signals)
        - Réception webhook depuis n8n en temps réel
        - Scoring / génération IA via Claude API
        - Création leads CRM en un clic (équipe Rénovation)
        - Calendrier de gestion de communauté intégré au module Projet
    """,
    'author': 'Agence Doorway',
    'depends': ['crm', 'project', 'mail', 'base_setup', 'intellix_branding', 'doorway_agents_dashboard', 'doorway_onboarding'],
    'data': [
        'security/veille_security.xml',
        'security/ir.model.access.csv',
        'data/onboarding.xml',
        'data/cron_sync.xml',
        'data/cron_reactivation.xml',
        'data/cron_reddit_oauth.xml',
        'wizards/create_lead_wizard_views.xml',
        'wizards/repondre_signal_wizard_views.xml',
        'wizards/reactivation_douce_wizard_views.xml',
        'wizards/reddit_oauth_code_wizard_views.xml',
        'views/veille_signal_views.xml',
        'views/veille_reactivation_views.xml',
        'views/veille_sources_views.xml',
        'views/community_schedule.xml',
        'views/veille_config_views.xml',
        'views/veille_dashboard.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'doorway_veille_sociale/static/src/xml/dashboard_templates.xml',
            'doorway_veille_sociale/static/src/js/dashboard.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
