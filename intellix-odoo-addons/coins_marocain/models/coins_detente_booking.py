# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDetenteBooking(models.Model):
    _name = 'coins.detente_booking'
    _description = 'coins.detente_booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    customer_id = fields.Many2one('res.partner', required=True)
    lead_id = fields.Many2one('crm.lead')
    package_id = fields.Many2one('coins.detente_package', required=True)
    currency_id = fields.Many2one('res.currency')
    name = fields.Char()
    status = fields.Char()
    source = fields.Char()
    booking_date = fields.Date()
    service_date = fields.Date()
    notes = fields.Text()
    cross_sell_amount = fields.Monetary(currency_field='currency_id')
    package_sale_price = fields.Monetary(currency_field='currency_id')
    package_cost = fields.Monetary(currency_field='currency_id')
    total_sale_price = fields.Monetary(currency_field='currency_id')
    total_cost = fields.Monetary(currency_field='currency_id')
    total_margin = fields.Monetary(currency_field='currency_id')
    active = fields.Boolean()
    cross_sell_added = fields.Boolean()
    margin_percent = fields.Float()
    participant_count = fields.Integer()
    min_participants = fields.Integer()
    below_min_participants = fields.Boolean()
    calendar_event_id = fields.Many2one('calendar.event')
    primary_partner_id = fields.Many2one('coins.detente_partner')
    calendar_color = fields.Integer()
    driver_id = fields.Many2one('coins.driver')
    pickup_address = fields.Char()
    dropoff_address = fields.Char()
    trip_status = fields.Char()
    confirmation_sent = fields.Boolean()
    confirmation_sent_at = fields.Datetime()
    service_time = fields.Float()
    payment_method = fields.Char()
    payment_status = fields.Char()
    payment_reference = fields.Char()
    referral_code = fields.Char()
    cross_sell_reminder = fields.Boolean()

    def action_cancel(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_confirm(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_deposit(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_mark_cross_sell(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_open_calendar_event(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_realize(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_resend_confirmation(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_reset_prospect(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

