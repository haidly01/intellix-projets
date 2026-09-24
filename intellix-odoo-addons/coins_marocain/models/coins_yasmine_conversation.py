# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsYasmineConversation(models.Model):
    _name = 'coins.yasmine.conversation'
    _description = 'coins.yasmine.conversation'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    partner_id = fields.Many2one('res.partner')
    turn_count = fields.Integer()
    name = fields.Char()
    session_id = fields.Char()
    language = fields.Char()
    intention_deduite = fields.Char()
    composition_groupe = fields.Char()
    rythme = fields.Char()
    signal_fort_type = fields.Char()
    state = fields.Char()
    carnet_badge_ref = fields.Char()
    raw_transcript = fields.Text()
    detail_libre = fields.Text()
    recommendation_narrative = fields.Text()
    score_confiance = fields.Float()
    signal_fort_detecte = fields.Boolean()
    hot_handoff_envoye = fields.Boolean()
    converti_en_reservation = fields.Boolean()
    completed = fields.Boolean()
    user_id = fields.Many2one('res.users')
    visitor_phone = fields.Char()
    visitor_name = fields.Char()
    visitor_email = fields.Char()
    contact_email_display = fields.Char()
    contact_name_display = fields.Char()
    contact_phone_display = fields.Char()
    transcript_html = fields.Text()
    can_prendre_relais = fields.Boolean()
    has_contact = fields.Boolean()

    activites_recommandees_ids = fields.Many2many('coins.activite', 'coins_yasmine_conv_activite_rel', 'conversation_id', 'activite_id', string = 'Activités recommandées')

    def action_creer_tache_suivi(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_open_activites(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_prendre_le_relais(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_save_contact(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_set_state_abandoned(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_set_state_hot_handoff(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_set_state_open(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_set_state_recommended(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

