# -*- coding: utf-8 -*-
"""Migration 19.0.2.11.0 — runbooks Phase 2 prêts à exécuter."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Runbook = env["intellix.support.runbook"].sudo()
    for code in ("calls_not_dialing", "lea_silent"):
        runbook = Runbook.search([("code", "=", code)], limit=1)
        if runbook and runbook.phase != "ready":
            runbook.write({"phase": "ready", "requires_approval": True})
            _logger.info("intellix_support migrate: runbook %s → ready", code)
