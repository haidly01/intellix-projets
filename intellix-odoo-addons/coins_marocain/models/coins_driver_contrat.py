# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDriverContrat(models.Model):
    _name = 'coins.driver.contrat'
    _description = 'coins.driver.contrat'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    chauffeur_id = fields.Many2one('coins.driver', required=True)
    signature_id = fields.Many2one('pe.electronic.signature')
    name = fields.Char()
    statut = fields.Char()
    token_signature = fields.Char()
    pdf_contrat_filename = fields.Char()
    contenu_html = fields.Text()
    active = fields.Boolean()
    date_envoi = fields.Datetime()
    date_signature = fields.Datetime()
    frais_par_course = fields.Float()
    my_activity_date_deadline = fields.Date()
    has_message = fields.Boolean()
    pdf_contrat = fields.Char()

    def action_envoyer_signature(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_marquer_refuse(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

