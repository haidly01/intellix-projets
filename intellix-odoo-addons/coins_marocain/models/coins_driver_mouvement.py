# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDriverMouvement(models.Model):
    _name = 'coins.driver.mouvement'
    _description = 'coins.driver.mouvement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    type = fields.Char()

    chauffeur_id = fields.Many2one('coins.driver', required=True)
    detente_booking_id = fields.Many2one('coins.detente_booking')
    reservation_id = fields.Integer()
    partenaire_id = fields.Many2one('coins.detente_partner')
    remise_quotidienne_id = fields.Many2one('coins.driver.remise_quotidienne')
    name = fields.Char()
    notes = fields.Char()
    partenaire_confirme_paye = fields.Boolean()
    partenaire_refus = fields.Boolean()
    date = fields.Datetime()
    montant = fields.Float()
    montant_partenaire_paye_directement = fields.Float()
    has_message = fields.Boolean()

    def action_partenaire_confirme(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_partenaire_non_recu(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

