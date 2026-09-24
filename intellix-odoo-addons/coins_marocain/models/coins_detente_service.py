# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDetenteService(models.Model):
    _name = 'coins.detente_service'
    _description = 'coins.detente_service'

    partner_id = fields.Many2one('coins.detente_partner', required=True)
    sequence = fields.Integer()
    currency_id = fields.Many2one('res.currency')
    name = fields.Char()
    category = fields.Char()
    duration_label = fields.Char()
    notes = fields.Char()
    list_price = fields.Monetary(currency_field='currency_id')
    partner_cost = fields.Monetary(currency_field='currency_id')
    active = fields.Boolean()
    is_pack = fields.Boolean()
