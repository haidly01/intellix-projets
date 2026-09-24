# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsWaSession(models.Model):
    _name = 'coins.wa.session'
    _description = 'coins.wa.session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    wa_log_ids = fields.Many2many('doorway.wa.log', string='Journal WhatsApp')
    wa_log_count = fields.Integer()

    phone = fields.Char()
    messages_json = fields.Text()
    lead_id = fields.Many2one('crm.lead')
    partner_id = fields.Many2one('res.partner')
    source = fields.Char()
    human_handoff = fields.Boolean()
    active = fields.Boolean()
    display_name = fields.Char()
    wa_log_count = fields.Integer()
    last_message = fields.Char()
    transcript_html = fields.Text()
    body = fields.Char()
    direction = fields.Char()
    external_sid = fields.Char()
    message_count = fields.Integer()
    name = fields.Char()
    provider = fields.Char()
    statut = fields.Char()

    def action_open_wa_logs(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True


    def action_reply_whatsapp(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True

