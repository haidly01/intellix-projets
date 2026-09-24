# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsActiviteBooking(models.Model):
    _name = 'coins.activite_booking'
    _description = 'coins.activite_booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    customer_id = fields.Many2one('res.partner', required=True)
    activite_id = fields.Many2one('coins.activite', required=True)
    participant_count = fields.Integer()
    currency_id = fields.Many2one('res.currency')
    name = fields.Char()
    status = fields.Char()
    source = fields.Char()
    booking_date = fields.Date()
    service_date = fields.Date()
    notes = fields.Text()
    unit_sale_price = fields.Monetary(currency_field='currency_id')
    unit_cost = fields.Monetary(currency_field='currency_id')
    total_sale_price = fields.Monetary(currency_field='currency_id')
    total_cost = fields.Monetary(currency_field='currency_id')
    total_margin = fields.Monetary(currency_field='currency_id')
    active = fields.Boolean()
    payment_method = fields.Char()
    payment_status = fields.Char()
    payment_reference = fields.Char()
    referral_code = fields.Char()
    my_activity_date_deadline = fields.Date()
    has_message = fields.Boolean()
