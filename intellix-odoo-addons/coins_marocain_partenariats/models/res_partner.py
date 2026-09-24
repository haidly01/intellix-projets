# -*- coding: utf-8 -*-
from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        restrict = self.env["sale.order"]._coins_restrict_devis_partners()
        uid = self.env.user.id
        for vals in vals_list:
            if restrict and not vals.get("user_id"):
                vals["user_id"] = uid
        return super().create(vals_list)
