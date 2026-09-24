# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Comptes CGNC paie + accès RH Paie Maroc pour les sociétés marocaines."""
    env["res.users"]._init_ensure_payroll_ma_groups()

    ResCompany = env["res.company"]
    for company in ResCompany.search([]):
        if not ResCompany._is_morocco_payroll_company(company):
            continue
        company._ensure_payroll_ma_accounts()
