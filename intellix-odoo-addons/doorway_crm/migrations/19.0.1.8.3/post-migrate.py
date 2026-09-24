# -*- coding: utf-8 -*-


def migrate(cr, version):
    env = cr.env if hasattr(cr, "env") else None
    if env is None:
        from odoo import api, SUPERUSER_ID

        env = api.Environment(cr, SUPERUSER_ID, {})
    env["mail.activity"]._doorway_migrate_existing_activities_to_calendar()
