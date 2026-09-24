# -*- coding: utf-8 -*-
from odoo import api, models

from ..hooks import setup_devis_workspace


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _coins_setup_devis_workspace(self):
        setup_devis_workspace(self.env)
        return True
