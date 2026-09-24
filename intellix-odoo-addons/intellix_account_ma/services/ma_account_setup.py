# -*- coding: utf-8 -*-
"""Configuration CGNC et comptes IntelliX pour les sociétés marocaines."""

import logging

_logger = logging.getLogger(__name__)

# Codes CGNC Odoo 19 (6 chiffres) — regroupements sémantiques spec IntelliX :
# 7124 → 712420 (études / licences SaaS)
# 7125 → 712430 (prestations services — VoIP, IA, extracteur)
# 7126 → 712720 (commissions — marketing géré)
# 7127 → 712420 (formation / setup)
REVENUE_ACCOUNTS = {
    "7124": "712420",
    "7125": "712430",
    "7126": "712720",
    "7127": "712420",
}

KEY_ACCOUNTS = {
    "3421": "342110",
    "4411": "441110",
    "4455": "445500",
    "3455": "345520",
    "34552": "345520",
    "5141": "514100",
    "6171": "617110",
    "6174": "617410",
    "4432": "443200",
    "4434": "443400",
    "4452": "445200",
    "4441": "444100",
}

PAYROLL_CODE_ALIASES = {
    "61711": ["61711", "617110"],
    "61741": ["61741", "617410"],
    "4432": ["4432", "443200"],
    "4433": ["4433", "443300"],
    "4452": ["4452", "445200"],
    "4441": ["4441", "444100"],
    "4434": ["4434", "443400"],
}

CATEGORY_REVENUE_MAP = {
    "Intellix": "7124",
    "Intellix / Call Center": "7125",
    "Intellix / Crédits IA": "7125",
    "Intellix / Marketing": "7126",
    "Intellix / Services": "7127",
}

CATEGORY_ANALYTIC_MAP = {
    "Intellix": "ANA-SALES",
    "Intellix / Call Center": "ANA-SALES",
    "Intellix / Crédits IA": "ANA-SALES",
    "Intellix / Marketing": "ANA-MKT",
    "Intellix / Services": "ANA-FORM",
}


def _is_morocco_company(company):
    ma = company.env.ref("base.ma", raise_if_not_found=False)
    return (
        company.x_intellix_accounting_region == "ma"
        or (ma and company.partner_id.country_id == ma)
    )


def ensure_cgnc_chart(env, company):
    """Charge le plan CGNC l10n_ma si la société n'a pas encore de comptes."""
    Account = env["account.account"].sudo()
    count = Account.search_count([("company_ids", "in", company.id)])
    if count >= 50:
        return count
    _logger.info(
        "IntelliX MA : chargement du plan CGNC pour %s (%s comptes existants)",
        company.name,
        count,
    )
    if company.chart_template:
        company.sudo().write({"chart_template": False})
    env["account.chart.template"].sudo().try_loading(
        "ma", company, install_demo=False, force_create=True
    )
    return Account.search_count([("company_ids", "in", company.id)])


def get_account_by_cgnc_code(env, company, semantic_code):
    """Retourne un compte par code sémantique (7124) ou code CGNC complet (712420)."""
    Account = env["account.account"].sudo()
    cgnc_code = KEY_ACCOUNTS.get(semantic_code) or REVENUE_ACCOUNTS.get(semantic_code) or semantic_code
    acc = Account.search(
        [("code", "=", cgnc_code), ("company_ids", "in", company.id)],
        limit=1,
    )
    if not acc and len(semantic_code) <= 4:
        acc = Account.search(
            [("code", "=like", f"{cgnc_code}%"), ("company_ids", "in", company.id)],
            limit=1,
            order="code",
        )
    return acc


def configure_moroccan_company(env, company):
    """Configure comptes, catégories, paie et société pour une entité MA."""
    if not _is_morocco_company(company):
        return

    ensure_cgnc_chart(env, company)

    if hasattr(company, "_ensure_payroll_ma_accounts"):
        company._ensure_payroll_ma_accounts()

    _map_product_categories(env, company)
    _set_company_accounting_defaults(env, company)
    _link_payroll_accounts(env, company)


def _map_product_categories(env, company):
    Category = env["product.category"].sudo()
    for cat_name, revenue_key in CATEGORY_REVENUE_MAP.items():
        cat = Category.search([("complete_name", "=", cat_name)], limit=1)
        if not cat:
            continue
        acc = get_account_by_cgnc_code(env, company, revenue_key)
        if acc:
            cat.with_company(company).property_account_income_categ_id = acc.id


def _set_company_accounting_defaults(env, company):
    receivable = get_account_by_cgnc_code(env, company, "3421")
    company = company.sudo()
    vals = {}
    if receivable:
        vals["account_default_pos_receivable_account_id"] = receivable.id
    tax_81 = env["account.tax"].sudo().search(
        [
            ("company_id", "=", company.id),
            ("type_tax_use", "=", "sale"),
            ("amount", "=", 20),
            ("name", "ilike", "81"),
        ],
        limit=1,
    )
    if tax_81:
        vals["account_sale_tax_id"] = tax_81.id
    income = get_account_by_cgnc_code(env, company, "7125")
    if income:
        vals["income_account_id"] = income.id
    if vals:
        company.sudo().write(vals)


def _link_payroll_accounts(env, company):
    """Associe les comptes CGNC aux règles salariales si les champs sont vides."""
    Rule = env["hr.salary.rule.ma"].sudo()
    if not Rule._name in env.registry:
        return
    mapping = {
        "BASIC": ("617110", "443200"),
        "CNSS_EMP": ("443200", "443300"),
        "CNSS_PAT": ("617410", "443300"),
        "AMO_EMP": ("443200", "443300"),
        "AMO_PAT": ("617410", "443300"),
        "CIMR_EMP": ("443200", "443300"),
        "CIMR_PAT": ("617410", "443300"),
        "IR": ("443200", "445200"),
    }
    for rule in Rule.search([("company_id", "=", company.id)]):
        codes = mapping.get(rule.code)
        if not codes:
            continue
        debit = get_account_by_cgnc_code(env, company, codes[0])
        credit = get_account_by_cgnc_code(env, company, codes[1])
        vals = {}
        if debit and not rule.account_debit_id:
            vals["account_debit_id"] = debit.id
        if credit and not rule.account_credit_id:
            vals["account_credit_id"] = credit.id
        if vals:
            rule.write(vals)


def _ensure_export_fiscal_setup(env, company):
    """Crée la taxe 0 % export et lie la position fiscale « Export de services »."""
    Tax = env["account.tax"].sudo()
    FP = env["account.fiscal.position"].sudo()
    Account = env["account.account"].sudo()
    FPA = env["account.fiscal.position.account"].sudo()

    src_taxes = Tax.search(
        [
            ("company_id", "=", company.id),
            ("type_tax_use", "=", "sale"),
            ("amount", "=", 20),
            ("active", "=", True),
        ]
    )
    if not src_taxes:
        return

    export_tax = Tax.search(
        [
            ("company_id", "=", company.id),
            ("name", "=", "TVA 0% export services"),
        ],
        limit=1,
    )
    if not export_tax:
        base_tax = Tax.search(
            [
                ("company_id", "=", company.id),
                ("name", "ilike", "0% 40"),
                ("type_tax_use", "=", "sale"),
            ],
            limit=1,
        )
        tax_group = base_tax.tax_group_id if base_tax else src_taxes[0].tax_group_id
        export_tax = Tax.create(
            {
                "name": "TVA 0% export services",
                "amount": 0,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": company.id,
                "tax_group_id": tax_group.id,
                "invoice_label": "Export services — exonéré (art. 92 CGI)",
                "original_tax_ids": [(6, 0, src_taxes.ids)],
            }
        )
    else:
        export_tax.write({"original_tax_ids": [(6, 0, src_taxes.ids)]})

    fp = env.ref(
        "intellix_account_ma.fiscal_position_export_services",
        raise_if_not_found=False,
    )
    if fp and fp.company_id == company:
        fp.write({"tax_ids": [(6, 0, [export_tax.id])]})
        account_pairs = [
            ("712420", "712520"),
            ("712430", "712530"),
            ("712720", "712530"),
        ]
        for src_code, dest_code in account_pairs:
            src = Account.search(
                [("code", "=", src_code), ("company_ids", "in", company.id)],
                limit=1,
            )
            dest = Account.search(
                [("code", "=", dest_code), ("company_ids", "in", company.id)],
                limit=1,
            )
            if not src or not dest:
                continue
            existing = FPA.search(
                [
                    ("position_id", "=", fp.id),
                    ("account_src_id", "=", src.id),
                ],
                limit=1,
            )
            if existing:
                existing.account_dest_id = dest.id
            else:
                FPA.create(
                    {
                        "position_id": fp.id,
                        "account_src_id": src.id,
                        "account_dest_id": dest.id,
                    }
                )

    ma_country = env.ref("base.ma", raise_if_not_found=False)
    domestic = FP.search(
        [
            ("company_id", "=", company.id),
            ("country_id", "=", ma_country.id if ma_country else False),
            ("auto_apply", "=", True),
        ],
        limit=1,
    )
    if domestic and domestic.name == "Morocco":
        domestic.name = "Maroc"


def _ensure_analytic_distributions(env, company):
    """Complète les distributions analytiques pour Marketing / Services / Extracteur."""
    Dist = env["account.analytic.distribution.model"].sudo()
    Category = env["product.category"].sudo()
    Analytic = env["account.analytic.account"].sudo()

    def _ana(code):
        return Analytic.search([("code", "=", code)], limit=1)

    mappings = [
        ("Intellix / Marketing", "ANA-MKT"),
        ("Intellix / Services", "ANA-FORM"),
    ]
    for cat_name, ana_code in mappings:
        cat = Category.search([("complete_name", "=", cat_name)], limit=1)
        ana = _ana(ana_code)
        if not cat or not ana:
            continue
        existing = Dist.search(
            [
                ("company_id", "=", company.id),
                ("product_categ_id", "=", cat.id),
            ],
            limit=1,
        )
        distribution = {str(ana.id): 100}
        if existing:
            existing.analytic_distribution = distribution
        else:
            Dist.create(
                {
                    "company_id": company.id,
                    "product_categ_id": cat.id,
                    "analytic_distribution": distribution,
                    "sequence": 15,
                }
            )


def setup_all_moroccan_companies(env):
    ResCompany = env["res.company"].sudo()
    for company in ResCompany.search([("x_intellix_accounting_region", "=", "ma")]):
        configure_moroccan_company(env, company)
        _ensure_export_fiscal_setup(env, company)
        _ensure_analytic_distributions(env, company)
    # Sociétés MA sans région encore renseignée (première installation)
    for company in ResCompany.search([("x_intellix_accounting_region", "=", False)]):
        if not _is_morocco_company(company):
            continue
        company.x_intellix_accounting_region = "ma"
        configure_moroccan_company(env, company)
        _ensure_export_fiscal_setup(env, company)
        _ensure_analytic_distributions(env, company)
