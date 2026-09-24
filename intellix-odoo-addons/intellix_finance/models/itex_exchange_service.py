# -*- coding: utf-8 -*-
from odoo import fields, models


class ItexExchangeService(models.Model):
    _name = "itex.exchange.service"
    _description = "Service d'échange ITEX"
    _order = "name"

    name = fields.Char(string="Service", required=True)
    active = fields.Boolean(default=True)
