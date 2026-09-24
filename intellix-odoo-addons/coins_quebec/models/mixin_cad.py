# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsQuebecCadMixin(models.AbstractModel):
    _name = "coins.quebec.cad.mixin"
    _description = "Devise CAD par défaut (Coins Québec)"

    @api.model
    def _cq_cad(self):
        cad = self.env.ref("base.CAD", raise_if_not_found=False)
        return cad or self.env.company.currency_id
