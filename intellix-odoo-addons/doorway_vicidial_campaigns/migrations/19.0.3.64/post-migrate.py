# -*- coding: utf-8 -*-
"""19.0.3.64 — hub Odoo WebRTC : heartbeat conf, campagnes B2B manual."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.doorway_vicidial_campaigns.hooks import (
        _backfill_human_agent_users,
        _ensure_frb2b_manual_campaigns,
    )

    _ensure_frb2b_manual_campaigns(env)
    _backfill_human_agent_users(env)
