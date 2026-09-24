# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsYasmineRelaisWizard(models.TransientModel):
    _name = 'coins.yasmine.relais.wizard'
    _description = 'coins.yasmine.relais.wizard'

    conversation_id = fields.Many2one('coins.yasmine.conversation', string='Conversation', ondelete='cascade', required=True)
    message = fields.Text(string='Message', required=True)
    phone = fields.Char(string='WhatsApp visiteur', help="Obligatoire pour envoyer. Saisissez-le si le chat ne l'a pas capté.")
    visitor_email = fields.Char(string='E-mail')
    visitor_name = fields.Char(string='Nom')


# --- reconstructed stubs ---

    def action_send_whatsapp(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True
