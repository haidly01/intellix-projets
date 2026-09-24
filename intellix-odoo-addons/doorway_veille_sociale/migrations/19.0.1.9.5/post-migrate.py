# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        from odoo.addons.doorway_veille_sociale.hooks import migrate_veille_settings_group

        migrate_veille_settings_group(env)
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_veille_sociale: migration 19.0.1.9.5 groupe config")
