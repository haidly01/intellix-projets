# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDetenteMassageType(models.Model):
    _name = 'coins.detente_massage_type'
    _description = 'coins.detente_massage_type'

    name = fields.Char()
    active = fields.Boolean()
