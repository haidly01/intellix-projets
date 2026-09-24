# -*- coding: utf-8 -*-
{
    "name": "Doorway Agents IA",
    "version": "19.0.3.1.0",
    "category": "CRM",
    "summary": "Dashboard performance agents IA — extension doorway_agents_dashboard",
    "description": """
        Fonctionnalités performance par agent et filtres par campagne.
        Menus et KPIs : doorway_agents_dashboard + doorway_vicidial_campaigns.
    """,
    "author": "Agence Doorway",
    "depends": [
        "doorway_agents_dashboard",
        "doorway_vicidial_campaigns",
    ],
    "data": [
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
