# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env["crm.lead"]._finance_harden_menus()
    created = env["crm.lead"]._finance_seed_demo_leads()
    env["crm.lead"]._finance_ensure_demo_segments()
    remapped = env["crm.lead"]._itex_ensure_funnel()
    _logger.info("intellix_finance: ITEX funnel remappé %s leads.", remapped)
    stats = env["crm.lead"].get_finance_dashboard_stats()
    driven = stats.get("driven") or {}
    growth = stats.get("growth_capital") or {}
    _logger.info(
        "intellix_finance: %s leads démo. Driven funnel=%s non_qualifiés=%s. "
        "Growth Capital funnel=%s non_qualifiés=%s. Aucun total croisé.",
        created,
        driven.get("in_funnel"),
        driven.get("not_qualified"),
        growth.get("in_funnel"),
        growth.get("not_qualified"),
    )
