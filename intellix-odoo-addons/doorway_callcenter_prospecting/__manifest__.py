# -*- coding: utf-8 -*-
{
    "name": "Doorway Prospection Call Centers MA/TN",
    "version": "19.0.1.2.0",
    "category": "Marketing",
    "summary": "Extraction call centers Maroc/Tunisie, validation Twilio, campagne WhatsApp Meta",
    "depends": [
        "base",
        "mail",
        "crm",
        "doorway_leads_bruts",
        "doorway_messaging",
        "doorway_social_ia",
        "renovation_conciergerie",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/crm_tags_stages.xml",
        "data/filter_defi_zakaria.xml",
        "data/ir_config_parameter.xml",
        "data/linkedin_config.xml",
        "data/cron_data.xml",
        "views/prospect_views.xml",
        "views/campagne_extraction_inherit.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "post_init_hook": "post_init_hook",
}
