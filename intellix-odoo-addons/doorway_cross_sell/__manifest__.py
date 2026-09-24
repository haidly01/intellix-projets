# -*- coding: utf-8 -*-
{
    "name": "Doorway — Cross-sell leads",
    "version": "19.0.1.0.13",
    "category": "Sales/CRM",
    "summary": "Lignes de cross-sell et bonus DH sur les opportunités existantes",
    "author": "Karine Barmaki / Agence Doorway",
    "depends": [
        "crm",
        "renovation_conciergerie",
        "reno_immobilier",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/doorway_cross_sell_line_views.xml",
        "views/crm_lead_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "doorway_cross_sell/static/src/css/reno_sheet.css",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
