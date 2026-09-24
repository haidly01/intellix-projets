# -*- coding: utf-8 -*-
{
    "name": "Coins Marocain",
    "version": "19.0.1.57.0",
    "category": "Services",
    "summary": "Plateforme curatée : biens, détente, activités, Yasmine, Carnet, chauffeurs",
    "description": """
Coins Marocain — module de gestion de la plateforme curatée.

Centralise dans Odoo :
- Biens, réservations, partenaires, chauffeurs
- Fiches propriétés + galerie + disponibilités Airbnb (iCal lecture seule)
- Contrats chauffeurs (signature OTP people_engine) + solde quotidien
- Forfaits détente paliers 1–8 + sync calendrier
- Activités / excursions (privatif + références Viator affiliation)
- Confirmations WhatsApp auto + portail chauffeur (lien magique)
- Tableau de bord global + dashboards détente / activités
- Concierge IA Yasmine (chat site + bot WhatsApp Twilio)
- Conversation d'accueil Yasmine (remplace le quiz) + hot-handoff
- Carnet du Voyageur (fidélité digitale) + Ambassadeurs
- Distribution OTA (Channex) : file fermeture + inbound + dossier conciergerie
""",
    "author": "IntelliX / Agence Doorway",
    "depends": [
        "base",
        "mail",
        "contacts",
        "crm",
        "calendar",
        "doorway_messaging",
        "web",
        "people_engine",
    ],
    "external_dependencies": {
        "python": ["icalendar", "requests", "stripe"],
    },
    "data": [
        "security/coins_security.xml",
        "security/ir.model.access.csv",
        "data/coins_sequence.xml",
        "data/coins_carnet_sequence.xml",
        "data/coins_wa_config.xml",
        "data/coins_detente_data.xml",
        "data/coins_calendar_data.xml",
        "data/coins_activite_data.xml",
        "data/coins_carnet_data.xml",
        "data/coins_yasmine_activity_data.xml",
        "data/coins_driver_ledger_data.xml",
        "data/coins_airbnb_ical_cron.xml",
        "data/coins_booking_icp.xml",
        "data/coins_partner_qualification_data.xml",
        "data/coins_crm_evenements_pipeline.xml",
        "data/coins_event_brief_data.xml",
        "data/coins_events_sheet_sync_data.xml",
        "data/coins_carte_data.xml",
        "data/coins_property_category_data.xml",
        "data/coins_fiche_video_view_cron.xml",
        "data/coins_channex_data.xml",
        "data/coins_channex_cron.xml",
        "data/coins_deco_prestataire_data.xml",
        "data/coins_deco_mail_template.xml",
        "wizard/coins_yasmine_relais_wizard_views.xml",
        "views/coins_channex_views.xml",
        "views/coins_property_views.xml",
        "views/coins_fiche_video_views.xml",
        "views/coins_partner_activity_views.xml",
        "views/coins_driver_views.xml",
        "views/coins_driver_ledger_views.xml",
        "views/coins_reservation_views.xml",
        "views/res_partner_views.xml",
        "views/coins_detente_partner_views.xml",
        "views/coins_detente_package_views.xml",
        "views/coins_detente_booking_views.xml",
        "views/coins_activite_views.xml",
        "views/coins_evenement_views.xml",
        "views/coins_prestataire_views.xml",
        "views/coins_deco_prestataire_views.xml",
        "views/crm_lead_evenement_views.xml",
        "views/crm_lead_deco_views.xml",
        "views/coins_yasmine_conversation_views.xml",
        "views/coins_wa_session_views.xml",
        "views/coins_carnet_views.xml",
        "views/coins_ambassador_views.xml",
        "views/coins_misc_views.xml",
        "views/coins_overview_views.xml",
        "views/coins_actions.xml",
        "views/coins_menus.xml",
        "templates/partenaire_portal.xml",
        "templates/partenaire_hebergement_ops.xml",
        "templates/partenaire_messages.xml",
        "templates/partenaire_dashboard.xml",
        "templates/deco_prestataire_portal.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "coins_marocain/static/src/css/detente_dashboard.css",
            "coins_marocain/static/src/xml/detente_dashboard.xml",
            "coins_marocain/static/src/js/detente_dashboard.js",
            "coins_marocain/static/src/xml/overview_dashboard.xml",
            "coins_marocain/static/src/js/overview_dashboard.js",
            "coins_marocain/static/src/xml/activite_dashboard.xml",
            "coins_marocain/static/src/js/activite_dashboard.js",
        ],
        "web.assets_web_dark": [
            "coins_marocain/static/src/css/detente_dashboard.css",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
