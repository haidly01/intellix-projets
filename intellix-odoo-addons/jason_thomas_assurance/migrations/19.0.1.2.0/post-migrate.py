# -*- coding: utf-8 -*-
from odoo.addons.jason_thomas_assurance.hooks import post_init_hook


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
