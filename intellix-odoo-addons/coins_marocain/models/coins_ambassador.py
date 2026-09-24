# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsAmbassador(models.Model):
    _name = 'coins.ambassador'
    _description = 'coins.ambassador'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    partner_id = fields.Many2one('res.partner', required=True)
    carnet_id = fields.Many2one('coins.carnet')
    name = fields.Char()
    code_parrainage = fields.Char()
    statut = fields.Char()
    type_ambassadeur = fields.Char()
    mode_paiement = fields.Char()
    origine = fields.Char()
    active = fields.Boolean()
    taux_commission = fields.Float()
    seuil_paiement_minimum = fields.Float()
    referral_count = fields.Integer()
    commission_pending = fields.Float()
    booking_amount = fields.Char()
    filleul_partner_id = fields.Many2one('res.partner')  # placeholder
    montant = fields.Char()
    statut_commission = fields.Char()

    referral_ids = fields.One2many('coins.ambassador.referral', 'ambassador_id', string = 'Parrainages')

    def action_activate(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_open_referrals(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


class CoinsAmbassadorReferral(models.Model):
    _name = 'coins.ambassador.referral'
    _description = 'coins.ambassador.referral'

    ambassador_id = fields.Many2one('coins.ambassador')
    referrer_partner_id = fields.Many2one('res.partner', required=True)
    carnet_id = fields.Many2one('coins.carnet')
    filleul_partner_id = fields.Many2one('res.partner')
    activite_booking_id = fields.Many2one('coins.activite_booking')
    detente_booking_id = fields.Many2one('coins.detente_booking')
    reservation_id = fields.Integer()
    name = fields.Char()
    statut_commission = fields.Char()
    notes = fields.Text()
    montant = fields.Float()
    booking_amount = fields.Float()
