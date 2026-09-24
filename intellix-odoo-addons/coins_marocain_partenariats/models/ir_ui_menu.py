# -*- coding: utf-8 -*-
from odoo import api, models

WORKSPACE_MENU_XMLIDS = (
    "coins_marocain.menu_coins_root",
    "coins_quebec.menu_cq_root",
    "reno_immobilier.menu_reno_immobilier_root",
    "sale.sale_menu_root",
    "doorway_messaging.menu_messaging_root",
    "crm.crm_menu_root",
    "intellix_riad.menu_riad_root",
)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def get_user_roots(self):
        roots = super().get_user_roots()
        if not self.env.user.has_group(
            "coins_marocain_partenariats.group_devis_workspace"
        ):
            return roots
        xmlids = roots._get_menuitems_xmlids()
        by_xml = {xmlids.get(menu.id): menu for menu in roots}
        ordered = self.browse()
        for xid in WORKSPACE_MENU_XMLIDS:
            menu = by_xml.get(xid)
            if menu:
                ordered |= menu
        return ordered

    def _load_menus_blacklist(self):
        res = list(super()._load_menus_blacklist() or [])
        if not self.env.user.has_group(
            "coins_marocain_partenariats.group_devis_workspace"
        ):
            return res
        roots = self.sudo().search([("parent_id", "=", False)])
        xmlids = roots._get_menuitems_xmlids()
        keep = set(WORKSPACE_MENU_XMLIDS)
        for menu in roots:
            if xmlids.get(menu.id) not in keep:
                res.append(menu.id)
        return res

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        if not self.env.user.has_group(
            "coins_marocain_partenariats.group_devis_workspace"
        ):
            return menus
        root = menus.get("root") or {}
        children = list(root.get("children") or [])
        by_xmlid = {
            (menus.get(mid) or {}).get("xmlid"): mid
            for mid in children
            if mid in menus
        }
        ordered = [
            by_xmlid[xid] for xid in WORKSPACE_MENU_XMLIDS if xid in by_xmlid
        ]
        extra = [mid for mid in children if mid not in ordered]
        root["children"] = ordered + extra
        menus["root"] = root
        return menus
