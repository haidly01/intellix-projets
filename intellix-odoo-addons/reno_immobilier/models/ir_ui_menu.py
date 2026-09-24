# -*- coding: utf-8 -*-
from odoo import api, models

# Home / 9-dot app order for Karine + Martin (and everyone else).
APP_MENU_ORDER = (
    "doorway_messaging.menu_messaging_root",
    "coins_marocain.menu_coins_root",
    "coins_quebec.menu_cq_root",
    "reno_immobilier.menu_reno_immobilier_root",
    "sale.sale_menu_root",
    "doorway_social_ia.menu_social_root",
)

APP_MENU_SEQUENCES = (
    ("doorway_messaging.menu_messaging_root", 1),
    ("coins_marocain.menu_coins_root", 2),
    ("coins_quebec.menu_cq_root", 3),
    ("reno_immobilier.menu_reno_immobilier_root", 4),
    ("sale.sale_menu_root", 5),
    ("doorway_social_ia.menu_social_root", 6),
)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        root = menus.get("root") or {}
        children = list(root.get("children") or [])
        by_xmlid = {
            (menus.get(mid) or {}).get("xmlid"): mid
            for mid in children
            if mid in menus
        }
        ordered = [by_xmlid[xid] for xid in APP_MENU_ORDER if xid in by_xmlid]
        extra = [mid for mid in children if mid not in ordered]
        root["children"] = ordered + extra
        menus["root"] = root
        return menus

    @api.model
    def _reno_align_app_menu_order(self):
        """Pin root app sequences so the 9-dot dashboard matches APP_MENU_ORDER."""
        Menu = self.sudo()
        for xmlid, sequence in APP_MENU_SEQUENCES:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.sequence != sequence:
                Menu.browse(menu.id).write({"sequence": sequence})
        return True
