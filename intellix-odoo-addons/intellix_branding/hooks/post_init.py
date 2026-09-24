# -*- coding: utf-8 -*-
import odoo
from odoo import SUPERUSER_ID, api


def _clear_assets_attachments(env):
    env["ir.attachment"].sudo().search(
        [
            ("public", "=", True),
            ("url", "like", "/web/assets/%"),
            ("res_model", "=", "ir.ui.view"),
            ("res_id", "=", 0),
        ]
    ).unlink()
    env.registry.clear_cache("assets")


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _clear_assets_attachments(env)


def uninstall_hook(cr, registry):
    post_init_hook(cr, registry)
