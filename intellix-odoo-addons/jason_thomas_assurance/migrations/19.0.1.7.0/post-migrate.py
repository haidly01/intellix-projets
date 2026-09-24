# -*- coding: utf-8 -*-
from odoo.addons.jason_thomas_assurance.hooks import _assign_platform_group


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    _assign_platform_group(env)
