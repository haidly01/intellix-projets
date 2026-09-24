# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    marketing = env.ref(
        "renovation_conciergerie.crm_team_marketing",
        raise_if_not_found=False,
    )
    sup_crm = env.ref(
        "renovation_conciergerie.group_pipeline_supervisor",
        raise_if_not_found=False,
    )
    zakaria = env["res.users"].search(
        [
            ("login", "=", "zakaria@agencedoorway.com"),
            ("active", "=", True),
            ("share", "=", False),
        ],
        limit=1,
    )
    if zakaria and marketing and not zakaria.doorway_assigned_pipeline_ids:
        profile = env["pe.employee.profile"].search(
            [("user_id", "=", zakaria.id)], limit=1
        )
        if profile:
            profile.write({"doorway_assigned_pipeline_ids": [(6, 0, marketing.ids)]})
        else:
            zakaria.sudo().write(
                {"doorway_assigned_pipeline_ids": [(6, 0, marketing.ids)]}
            )
    if zakaria and sup_crm and sup_crm not in zakaria.group_ids:
        zakaria.sudo().write({"group_ids": [(4, sup_crm.id)]})
