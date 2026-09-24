# -*- coding: utf-8 -*-
{
    "name": "Doorway — Qualification Hiba / Coins Québec",
    "version": "19.0.1.7.5",
    "category": "Sales/CRM",
    "summary": "Pipeline Coins Québec, RDV Martin, pointage et paie freelance Hiba",
    "depends": [
        "crm",
        "calendar",
        "hr",
        "hr_attendance",
        "people_engine",
        "coins_marocain",
        "renovation_conciergerie",
    ],
    "data": [
        "security/groups.xml",
        "security/hr_attendance_rule.xml",
        "security/ir.model.access.csv",
        "data/pipeline.xml",
        "views/crm_lead_views.xml",
        "views/wizard_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_hiba_qualif/static/src/js/pe_rh_hub_hiba.js",
            "doorway_hiba_qualif/static/src/xml/pe_rh_hub_hiba.xml",
            "doorway_hiba_qualif/static/src/js/hiba_martin_slots.js",
            "doorway_hiba_qualif/static/src/xml/hiba_martin_slots.xml",
            "doorway_hiba_qualif/static/src/css/hiba_martin_slots.css",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
