# -*- coding: utf-8 -*-
from odoo.addons.jason_thomas_assurance.hooks import (
    _backfill_birth_dates,
    _recompute_anniversaries,
    post_init_hook,
)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    _backfill_birth_dates(env)
    _recompute_anniversaries(env)
