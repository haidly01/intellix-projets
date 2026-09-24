from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _filter_visible_menus(self):
        menus = super()._filter_visible_menus()
        if self.env.user.has_group("base.group_system"):
            return menus
        if not self.env.user.has_group("renovation_conciergerie.group_renovation_partner"):
            return menus

        allowed_root_ids = set()
        for xmlid in ("renovation_conciergerie.menu_partner_root",):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                allowed_root_ids.add(menu.id)

        if not allowed_root_ids:
            return menus

        def _root_id(menu):
            current = menu
            while current.parent_id:
                current = current.parent_id
            return current.id

        return menus.filtered(lambda menu: _root_id(menu) in allowed_root_ids)
