# -*- coding: utf-8 -*-
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = "res.users"

    demo_call_center = fields.Boolean(
        string="Demo Call Center",
        compute="_compute_demo_call_center",
        store=True,
    )

    @api.depends("group_ids")
    def _compute_demo_call_center(self):
        group = self.env.ref(
            "doorway_demo_call_center.group_demo_call_center",
            raise_if_not_found=False,
        )
        for user in self:
            user.demo_call_center = bool(group and group in user.group_ids)

    def _is_demo_call_center_user(self):
        self.ensure_one()
        return bool(self.demo_call_center)

    def action_resend_demo_invitation(self):
        """Renvoie l'e-mail d'accès Intellix (demo call center)."""
        from odoo.addons.doorway_demo_call_center.services.demo_provisioning import (
            DemoCallCenterProvisioning,
        )

        self.ensure_one()
        if not self.demo_call_center:
            raise UserError(_("Cet utilisateur n'est pas un compte Demo Call Center."))
        password = secrets.token_urlsafe(10)
        self.sudo().write({"password": password, "active": True})
        DemoCallCenterProvisioning(self.env).send_access_invitation(self, password)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Invitation envoyée"),
                "message": _("E-mail d'accès envoyé à %s.") % (self.login or self.email),
                "type": "success",
                "sticky": False,
            },
        }
