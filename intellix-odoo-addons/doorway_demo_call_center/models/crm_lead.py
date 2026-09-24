# -*- coding: utf-8 -*-
from odoo import api, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        if user.demo_call_center:
            for vals in vals_list:
                vals.setdefault("company_id", user.company_id.id)
        return super().create(vals_list)
