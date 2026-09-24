# -*- coding: utf-8 -*-
import logging
import secrets

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Génère intellix_support.api_token si absent (intégrations n8n)."""
    icp = env["ir.config_parameter"].sudo()
    key = "intellix_support.api_token"
    existing = (icp.get_param(key) or "").strip()
    if not existing:
        token = secrets.token_urlsafe(32)
        icp.set_param(key, token)
        _logger.info("intellix_support: token API support généré automatiquement.")

    Runbook = env["intellix.support.runbook"].sudo()
    for code in ("calls_not_dialing", "lea_silent"):
        runbook = Runbook.search([("code", "=", code)], limit=1)
        if runbook and runbook.phase != "ready":
            runbook.write({"phase": "ready", "requires_approval": True})
            _logger.info("intellix_support: runbook %s → phase ready", code)
