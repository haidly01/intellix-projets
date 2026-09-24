# -*- coding: utf-8 -*-
{
    "name": "Intellix — Catalogue produits",
    "version": "19.0.2.2.1",
    "category": "Sales",
    "summary": "Catalogue Coins Marocain : devis Digital Doorway (dh) et Agence Doorway ($CAD)",
    "depends": ["product", "sale_management", "intellix_branding"],
    "data": [
        "security/ir.model.access.csv",
        "data/enable_quotation_templates.xml",
        "data/intellix_product_category.xml",
        "data/intellix_cm_products.xml",
        "data/intellix_cm_quotation_templates.xml",
        "data/ix_category_videos.xml",
        "views/intellix_product_views.xml",
        "views/intellix_quotation_template_views.xml",
        "views/intellix_category_video_views.xml",
        "views/intellix_sale_menus.xml",
        "views/intellix_sale_order_views.xml",
        "views/intellix_sale_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "intellix_catalog/static/src/scss/intellix_quotation_templates.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "license": "LGPL-3",
}
