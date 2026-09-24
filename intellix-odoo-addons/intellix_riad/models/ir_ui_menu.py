# -*- coding: utf-8 -*-

from odoo import models


class IrUiMenuRiad(models.Model):
    _inherit = "ir.ui.menu"

    def _visible_menu_ids(self, debug=False):
        menu_ids = super()._visible_menu_ids(debug=debug)
        user = self.env.user
        is_riad_owner = user.has_group("intellix_riad.group_riad_user") and not user.has_group(
            "intellix_riad.group_riad_manager"
        )
        if is_riad_owner:
            messaging_root = self.env["ir.model.data"]._xmlid_to_res_id(
                "doorway_messaging.menu_messaging_root", raise_if_not_found=False
            )
            if messaging_root:
                menu_ids = menu_ids - {messaging_root}
        return menu_ids
