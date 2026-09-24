# -*- coding: utf-8 -*-
from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_open_business_card_scan(self):
        self.ensure_one()
        return self.env["doorway.business.card"].action_open_scan_client(
            target_model="res.partner",
            record_id=self.id,
        )
