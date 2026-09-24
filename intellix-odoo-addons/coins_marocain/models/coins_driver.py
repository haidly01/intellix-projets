# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsDriver(models.Model):
    _name = 'coins.driver'
    _description = 'coins.driver'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    partner_id = fields.Many2one('res.partner')
    name = fields.Char()
    phone = fields.Char()
    email = fields.Char()
    state = fields.Char()
    loyalty_notes = fields.Text()
    active = fields.Boolean()
    rating = fields.Float()
    portal_token = fields.Char()
    portal_last_access = fields.Datetime()
    contrat_id = fields.Many2one('coins.driver.contrat')
    contrat_statut = fields.Char()  # was Selection(related = 'contrat_id.statut', string = )
    mode_remise = fields.Char()
    rib_coordonnees = fields.Char()
    has_contrat_signe = fields.Boolean()
    solde_du_jour = fields.Float()
    trips_count = fields.Integer()
    portal_url = fields.Char()
    customer_id = fields.Many2one('res.partner')  # placeholder
    date = fields.Char()
    date_signature = fields.Char()
    frais_par_course = fields.Char()
    heure_rencontre = fields.Char()
    montant = fields.Char()
    montant_total_du = fields.Char()
    remise_quotidienne_id = fields.Many2one('res.partner')  # placeholder
    service_date = fields.Char()
    service_time = fields.Char()
    status = fields.Char()
    statut = fields.Char()
    trip_status = fields.Char()

    reservation_ids = fields.One2many('coins.reservation', 'driver_id', string = 'Trajets / réservations')
    detente_booking_ids = fields.One2many('coins.detente_booking', 'driver_id', string = 'Courses détente')
    contrat_ids = fields.One2many('coins.driver.contrat', 'chauffeur_id', string = 'Contrats')
    mouvement_ids = fields.One2many('coins.driver.mouvement', 'chauffeur_id', string = 'Mouvements')
    remise_ids = fields.One2many('coins.driver.remise_quotidienne', 'chauffeur_id', string = 'Remises quotidiennes')

    def action_creer_contrat(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_open_contrat(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_regenerate_portal_link(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_send_portal_link_whatsapp(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

