# -*- coding: utf-8 -*-
{
    "name": "Intellix — Charte graphique",
    "version": "19.0.3.20.14",
    "category": "Hidden",
    "summary": "Design system Intellix (dark/light, DM Sans, indigo/violet)",
    "depends": ["web", "portal", "crm", "http_routing", "website", "spreadsheet_dashboard"],
    "auto_install": True,
    "data": [
        "data/assets.xml",
        "views/login_branding.xml",
        "views/website_login_branding.xml",
        "views/web_favicon.xml",
        "views/web_layout_fonts.xml",
        "views/webclient_branding.xml",
        "views/style_guide_page.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            "intellix_branding/static/src/scss/primary_variables.scss",
        ],
        "web.assets_frontend": [
            "intellix_branding/static/src/scss/intellix_tokens.scss",
            "intellix_branding/static/src/scss/intellix_branding.scss",
        ],
        "web.assets_web_dark": [
            "intellix_branding/static/src/scss/intellix_primary.dark.scss",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
