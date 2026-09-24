# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.doorway_vicidial_campaigns.hooks import _backfill_human_agent_users

    _backfill_human_agent_users(env)
