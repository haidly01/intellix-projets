# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    from odoo.addons.doorway_demo_call_center.services.demo_provisioning import (
        DemoCallCenterProvisioning,
    )

    try:
        result = DemoCallCenterProvisioning(env).provision_pilot_abdallah()
        if result.get("password"):
            _logger.info(
                "Pilote demo Abdallah — login %s — mot de passe temporaire : %s",
                result.get("login"),
                result.get("password"),
            )
    except Exception:  # noqa: BLE001
        _logger.exception("Échec provisionnement pilote demo Abdallah")
