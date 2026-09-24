# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.attachment"].sudo().search(
        [
            ("public", "=", True),
            ("url", "like", "/web/assets/%"),
            ("res_model", "=", "ir.ui.view"),
            ("res_id", "=", 0),
        ]
    ).unlink()
    env.registry.clear_cache("assets")
