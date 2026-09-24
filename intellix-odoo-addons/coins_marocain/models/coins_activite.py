# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsActivite(models.Model):
    _name = 'coins.activite'
    _description = 'coins.activite'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    currency_id = fields.Many2one('res.currency')
    partner_id = fields.Many2one('res.partner')
    name = fields.Char()
    category = fields.Char()
    operator = fields.Char()
    viator_affiliate_link = fields.Char()
    duration = fields.Char()
    blog_article_link = fields.Char()
    description = fields.Text()
    public_price = fields.Monetary(currency_field='currency_id')
    partner_price = fields.Monetary(currency_field='currency_id')
    estimated_margin = fields.Monetary(currency_field='currency_id')
    active = fields.Boolean()
    is_bookable = fields.Boolean()
    badge_categorie = fields.Char()
    is_vip_catalogue = fields.Boolean()
    booking_count = fields.Integer()
    activity_type = fields.Char()

    booking_ids = fields.One2many('coins.activite_booking', 'activite_id', string = 'Réservations')

    def action_open_viator_link(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_view_bookings(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

