# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        count = env["mail.activity"]._doorway_migrate_existing_activities_to_calendar()
        _logger.info(
            "doorway_crm migration %s: %s activité(s) CRM migrée(s) vers le calendrier",
            version,
            count,
        )
    except Exception:
        _logger.exception("doorway_crm: échec migration one-shot calendrier activités")
