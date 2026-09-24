# -*- coding: utf-8 -*-

from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _sync_pipeline_tab_groups(self):
        super()._sync_pipeline_tab_groups()
        team = self.env.ref(
            "doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False
        )
        group = self.env.ref(
            "doorway_hiba_qualif.group_pipeline_tab_coins_quebec",
            raise_if_not_found=False,
        )
        if not team or not group:
            return
        for user in self:
            if user.share or not user.active:
                continue
            should = team in user.doorway_assigned_pipeline_ids or user.login in (
                "martin@agencedoorway.com",
                "hiba@agencedoorway.com",
                "leiladaouadi@gmail.com",
            )
            has = group in user.group_ids
            if should and not has:
                user.sudo().write({"group_ids": [(4, group.id)]})
            elif not should and has:
                user.sudo().write({"group_ids": [(3, group.id)]})
