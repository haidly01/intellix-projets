# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

CALL_CENTER_CODES = (
    "INTLX-VOIP-CC-S",
    "INTLX-VOIP-CC-L",
    "INTLX-CC-SAAS",
    "INTLX-SETUP-CC",
    "INTLX-IA-M",
    "INTLX-IA-L",
    "INTLX-IA-XL",
)

CALL_CENTER_TEMPLATE_NAMES = (
    "Call Center — 10 agents",
    "Call Center — 30 agents",
    "Call Center — 50 agents",
    "Marketing Géré — Budget Starter",
    "Marketing Géré — Budget Scale",
    "Call Center 30 agents + Marketing Géré",
)

CM_TEMPLATE_NAMES = (
    "Starter Intellix",
    "Croissance IA",
    "Présence Digitale Complète",
)


def _archive_call_center(env):
    Product = env["product.template"].sudo()
    products = Product.search(
        [
            "|",
            "|",
            ("default_code", "in", CALL_CENTER_CODES),
            ("default_code", "=like", "INTLX-%"),
            ("categ_id.name", "in", ("Call Center", "Crédits IA")),
        ]
    )
    if products:
        products.write({"active": False, "sale_ok": False})
        _logger.info("intellix_catalog: %s produits call center archivés", len(products))

    Template = env["sale.order.template"].sudo()
    templates = Template.search([("name", "in", CALL_CENTER_TEMPLATE_NAMES)])
    if templates:
        templates.write({"active": False})
        _logger.info("intellix_catalog: %s modèles call center archivés", len(templates))
    return len(products), len(templates)


def _share_templates_across_companies(env):
    Template = env["sale.order.template"].sudo()
    templates = Template.search([("name", "in", CM_TEMPLATE_NAMES)])
    if templates:
        templates.write({"company_id": False})
    return len(templates)


def _normalize_intellix_product_taxes(env):
    Product = env["product.template"].sudo()
    companies = env["res.company"].sudo().search([])
    tax_by_company = {}
    for company in companies:
        tax = env["account.tax"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("type_tax_use", "=", "sale"),
                ("active", "=", True),
            ],
            order="id asc",
            limit=1,
        )
        if tax:
            tax_by_company[company.id] = tax

    updated = 0
    codes = [
        "INTELLIX_BASE",
        "AGENT_IA_ABO",
        "AGENT_IA_CONCEPTION_NEUF",
        "AGENT_IA_CONCEPTION_REPRISE",
        "AGENT_IA_BUNDLE_S",
        "AGENT_IA_BUNDLE_M",
        "AGENT_IA_BUNDLE_L",
        "AGENT_IA_DEPASSEMENT",
        "SITE_WEB_SIMPLE",
        "SITE_WEB_STANDARD",
        "SITE_WEB_PREMIUM",
        "MAINTENANCE_SITE",
        "SEO_ESSENTIEL",
        "SEO_CROISSANCE",
        "SEO_INTENSIF",
        "PERSONNALISATION_INTELLIX",
    ]
    for product in Product.search([("default_code", "in", codes)]):
        taxes = env["account.tax"]
        for company in companies:
            if company.id in tax_by_company:
                taxes |= tax_by_company[company.id]
        vals = {"company_id": False}
        if taxes and set(product.taxes_id.ids) != set(taxes.ids):
            vals["taxes_id"] = [(6, 0, taxes.ids)]
        product.write(vals)
        updated += 1
    if updated:
        _logger.info("intellix_catalog: taxes / société sur %s produits CM", updated)
    return updated


def _ensure_pricelists(env):
    Currency = env["res.currency"].sudo()
    Pricelist = env["product.pricelist"].sudo()
    for name, iso in (("IX-MAD", "MAD"), ("IX-CAD", "CAD")):
        currency = Currency.search([("name", "=", iso)], limit=1)
        if not currency:
            currency = Currency.create(
                {"name": iso, "symbol": "dh" if iso == "MAD" else "$CAD", "full_name": iso}
            )
        elif not currency.active:
            currency.active = True
        existing = Pricelist.search([("name", "=", name)], limit=1)
        if not existing:
            Pricelist.create(
                {"name": name, "currency_id": currency.id, "company_id": False}
            )


def post_init_hook(env):
    template_group = env.ref(
        "sale_management.group_sale_order_template", raise_if_not_found=False
    )
    if template_group:
        sales_groups = (
            env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
            | env.ref("sales_team.group_sale_manager", raise_if_not_found=False)
        )
        if sales_groups:
            users = env["res.users"].sudo().search(
                [("group_ids", "in", sales_groups.ids)]
            )
            for user in users:
                if template_group not in user.group_ids:
                    user.sudo().write({"group_ids": [(4, template_group.id)]})

    try:
        _archive_call_center(env)
        _ensure_pricelists(env)
        _share_templates_across_companies(env)
        _normalize_intellix_product_taxes(env)
    except Exception:  # noqa: BLE001
        _logger.exception("intellix_catalog: maintenance catalogue impossible")
