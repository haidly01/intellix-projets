# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    profiles = env["pe.employee.profile"].search([("pe_status", "!=", "inactive")])
    if profiles:
        profiles.action_calculate_score(calculated_by="auto")
