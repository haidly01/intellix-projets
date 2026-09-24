# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDetentePackage(models.Model):
    _name = 'coins.detente_package'
    _description = 'coins.detente_package'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    currency_id = fields.Many2one('res.currency')
    name = fields.Char()
    package_type = fields.Char()
    description = fields.Text()
    sale_price = fields.Monetary(currency_field='currency_id')
    estimated_cost = fields.Monetary(currency_field='currency_id')
    estimated_margin = fields.Monetary(currency_field='currency_id')
    active = fields.Boolean()
    margin_percent = fields.Float()
    min_participants = fields.Integer()
    is_limited_test = fields.Boolean()
    booking_count = fields.Integer()
    my_activity_date_deadline = fields.Date()
    has_message = fields.Boolean()
    is_chef_multi_service = fields.Boolean()
    neighborhood = fields.Char()
    partner_price_bbq_chef = fields.Char()
    partner_price_cours_cuisine = fields.Char()
    partner_price_dinner_show = fields.Char()
    partner_price_dj_soiree = fields.Char()
    partner_price_fermette_journee = fields.Char()
    partner_price_hammam_massage = fields.Char()
    partner_price_pool = fields.Char()
    partner_price_sortie_soiree = fields.Char()
    partner_type = fields.Char()
    verdict = fields.Char()

    partner_ids = fields.Many2many('coins.detente_partner', 'coins_detente_package_partner_rel', 'package_id', 'partner_id', string = 'Partenaires', help = 'Partenaires directs (hors Viator) qui composent ce forfait.')
    suggested_chef_ids = fields.Many2many('coins.detente_partner', 'coins_detente_package_suggested_chef_rel', 'package_id', 'partner_id', string = 'Chefs multi-service suggérés', compute = '_compute_suggested_chefs')
    booking_ids = fields.One2many('coins.detente_booking', 'package_id', string = 'Réservations')

    def action_add_suggested_chef(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_view_bookings(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

