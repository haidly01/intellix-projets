# -*- coding: utf-8 -*-
from odoo import api, models

PAYROLL_MA_MANAGER_PARENT_XMLIDS = (
    "people_engine.group_admin",
    "base.group_system",
    "hr.group_hr_manager",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _ensure_payroll_ma_groups(self):
        """Accorde les groupes Paie Maroc aux RH et superadmins existants."""
        group_user = self.env.ref(
            "intellix_hr_payroll_ma.group_hr_payroll_ma_user",
            raise_if_not_found=False,
        )
        group_manager = self.env.ref(
            "intellix_hr_payroll_ma.group_hr_payroll_ma_manager",
            raise_if_not_found=False,
        )
        if not group_user or not group_manager:
            return

        for user in self:
            if not user.active or user.share:
                continue
            if any(user.has_group(xmlid) for xmlid in PAYROLL_MA_MANAGER_PARENT_XMLIDS):
                missing = (group_user | group_manager) - user.group_ids
            elif user.has_group("people_engine.group_hr"):
                missing = group_user - user.group_ids
            else:
                continue
            if missing:
                user.sudo().write({"group_ids": [(4, group.id) for group in missing]})

    @api.model
    def _init_ensure_payroll_ma_groups(self):
        """Upgrade / post-init : aligne les accès Paie Maroc."""
        users = self.search([("active", "=", True), ("share", "=", False)])
        users._ensure_payroll_ma_groups()
