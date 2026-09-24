# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDriverRemise(models.Model):
    _name = 'coins.driver.remise_quotidienne'
    _description = 'coins.driver.remise_quotidienne'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    chauffeur_id = fields.Many2one('coins.driver', required=True)
    name = fields.Char()
    statut = fields.Char()
    date = fields.Date()
    notes = fields.Text()
    heure_rencontre = fields.Datetime()
    montant_total_du = fields.Float()
    my_activity_date_deadline = fields.Date()
    has_message = fields.Boolean()
    montant = fields.Char()
    partenaire_refus = fields.Char()

    mouvements_ids = fields.One2many('coins.driver.mouvement', 'remise_quotidienne_id', string = 'Mouvements')

    def action_marquer_reconciliee(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_marquer_remise(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

