# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsCarnet(models.Model):
    _name = 'coins.carnet'
    _description = 'coins.carnet'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    partner_id = fields.Many2one('res.partner', required=True)
    nombre_badges = fields.Integer()
    nombre_parrainages_valides = fields.Integer()
    name = fields.Char()
    palier_actuel = fields.Char()  # was Selection(PALIER_SELECTION, string = 'Palier actue)
    code_parrainage = fields.Char()
    portal_token = fields.Char()
    date_premier_badge = fields.Date()
    date_dernier_badge = fields.Date()
    eligible_programme_ambassadeur = fields.Boolean()
    catalogue_vip_debloque = fields.Boolean()
    ambassador_notified = fields.Boolean()
    active = fields.Boolean()
    animation_premium = fields.Boolean()
    activite_booking_id = fields.Many2one('coins.activite_booking')
    activite_id = fields.Many2one('coins.activite')
    categorie_badge = fields.Char()
    date_obtention = fields.Char()
    detente_booking_id = fields.Many2one('coins.detente_booking')
    display_name_badge = fields.Char()

    badge_ids = fields.One2many('coins.carnet.badge', 'carnet_id', string = 'Badges')
    favori_ids = fields.One2many(
        'coins.carnet.favori',
        'carnet_id',
        string='Favoris carte',
    )

    def action_open_badges(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


class CoinsCarnetBadge(models.Model):
    _name = 'coins.carnet.badge'
    _description = 'coins.carnet.badge'

    carnet_id = fields.Many2one('coins.carnet', required=True)
    partner_id = fields.Many2one('res.partner')
    activite_booking_id = fields.Many2one('coins.activite_booking')
    detente_booking_id = fields.Many2one('coins.detente_booking')
    reservation_id = fields.Integer()
    activite_id = fields.Many2one('coins.activite')
    categorie_badge = fields.Char()  # was Selection(BADGE_CATEGORIES, string = 'Catégorie', )
    display_name_badge = fields.Char()
    notes = fields.Char()
    date_obtention = fields.Date()
    unlock_celebrated = fields.Boolean()
    name = fields.Char()
