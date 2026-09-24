# -*- coding: utf-8 -*-
{
    "name": "IntelliX — Comptabilité Maroc (CGNC)",
    "version": "19.0.1.1.0",
    "category": "Accounting/Localizations",
    "summary": "Plan CGNC, TVA, analytique modules et routage MA/CA — Digital Doorway",
    "description": """
        Configuration comptable marocaine IntelliX : plan CGNC, positions fiscales
        (Maroc 20 % / export services 0 %), comptes de produits par module,
        analytique (Sales, RH, Formation, Marketing, TM, Extracteur) et routage
        multi-société Maroc vs Canada.

        Les devis et factures clients canadiens sont comptabilisés dans Agence
        Doorway Inc. ; les opérations marocaines et export depuis le Maroc passent
        par Digital Doorway SARL.
    """,
    "author": "Agence Doorway Inc.",
    "depends": [
        "account",
        "sale",
        "analytic",
        "l10n_ma",
        "intellix_catalog",
        "intellix_hr_dossier",
        "intellix_hr_payroll_ma",
    ],
    "data": [
        "data/res_country_group_data.xml",
        "data/analytic_plan_data.xml",
        "data/fiscal_position_data.xml",
        "data/product_category_mapping.xml",
        "data/analytic_distribution_data.xml",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
