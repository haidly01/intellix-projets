# -*- coding: utf-8 -*-
{
    "name": "Doorway — Visites guidées",
    "version": "19.0.1.0.1",
    "category": "Hidden",
    "summary": "Onboarding gamifié partagé pour les applications Doorway",
    "description": "Visite guidée, badges, confettis et progression XP pour tous les modules Doorway.",
    "author": "Agence Doorway Inc.",
    "depends": ["web", "mail", "intellix_branding"],
    "data": [
        "security/ir.model.access.csv",
        "views/doorway_onboarding_wizard.xml",
        "data/tour_people_engine.xml",
        "data/tour_veille_sociale.xml",
        "data/tour_renovation.xml",
        "data/tour_agents_ia.xml",
        "data/tour_credits.xml",
        "data/tour_lead_automation.xml",
        "data/tour_vicidial_call_center.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_onboarding/static/src/doorway_onboarding/doorway_onboarding.scss",
            "doorway_onboarding/static/src/doorway_onboarding/doorway_onboarding_confetti.js",
            "doorway_onboarding/static/src/doorway_onboarding/doorway_onboarding_form_controller.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
