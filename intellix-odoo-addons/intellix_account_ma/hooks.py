# -*- coding: utf-8 -*-
import logging

from .services.ma_account_setup import setup_all_moroccan_companies

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Configure le plan CGNC, l'analytique et les mappings IntelliX."""
    _logger.info("IntelliX MA : post-init comptabilité Maroc")
    setup_all_moroccan_companies(env)

    ResCompany = env["res.company"].sudo()
    ma = ResCompany._intellix_ma_company()
    ca = ResCompany._intellix_ca_company()
    if ma and not ma.x_intellix_accounting_region:
        ma.x_intellix_accounting_region = "ma"
    if ca and not ca.x_intellix_accounting_region:
        ca.x_intellix_accounting_region = "ca"

    _disable_import_export_auto_apply(env, ma)

    _logger.info(
        "IntelliX MA : configuration terminée (MA=%s, CA=%s)",
        ma.name if ma else "N/A",
        ca.name if ca else "N/A",
    )


def _disable_import_export_auto_apply(env, ma_company):
    """Désactive l'auto-détection Import/Export au profit d'Export de services."""
    if not ma_company:
        return
    fp = env["account.fiscal.position"].sudo().search(
        [
            ("company_id", "=", ma_company.id),
            ("name", "in", ["Import/Export", "Importation/Exportation"]),
        ],
        limit=1,
    )
    if fp and fp.auto_apply:
        fp.write({"auto_apply": False, "sequence": 50})
