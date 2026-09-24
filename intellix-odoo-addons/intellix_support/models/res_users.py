# -*- coding: utf-8 -*-
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.depends("name", "login", "partner_id")
    @api.depends_context("support_ticket_user_picker")
    def _compute_display_name(self):
        if not self.env.context.get("support_ticket_user_picker"):
            return super()._compute_display_name()
        for user in self.sudo():
            partner = user.partner_id
            if not partner:
                user.display_name = user.login or str(user.id)
            elif partner.is_company:
                user.display_name = f"{user.login} — {partner.name}"
            elif partner.parent_id:
                user.display_name = f"{partner.name} ({partner.parent_id.name})"
            else:
                user.display_name = partner.name or user.login

    @api.model
    def _intellix_support_sync_platform_users(self):
        """Onboarding : accorde Support Utilisateur à tous les utilisateurs internes."""
        group = self.env.ref(
            "intellix_support.group_intellix_support_user",
            raise_if_not_found=False,
        )
        if not group:
            return
        users = self.search([("share", "=", False), ("active", "=", True)])
        missing = users.filtered(
            lambda u: u.has_group("base.group_user")
            and group not in u.group_ids
        )
        if missing:
            missing.sudo().write({"group_ids": [(4, group.id)]})
