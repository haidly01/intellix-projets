# -*- coding: utf-8 -*-

from odoo import fields, models


class BabinvestConciergeInteraction(models.Model):
    _name = "babinvest.concierge.interaction"
    _description = "Journal des relances — conciergerie Bab Invest"
    _order = "sent_date desc"

    lead_id = fields.Many2one(
        "babinvest.concierge.lead", string="Lead", required=True, ondelete="cascade", index=True
    )
    channel = fields.Selection(
        [
            ("whatsapp", "WhatsApp"),
            ("email", "Email"),
            ("appel_sofia", "Appel Sofia (IA)"),
            ("appel_humain", "Appel humain"),
            ("sms", "SMS"),
        ],
        required=True,
    )
    template_used = fields.Char(string="Gabarit utilisé")
    sent_date = fields.Datetime(string="Envoyé le", default=fields.Datetime.now, required=True)
    response_received = fields.Boolean(string="Réponse reçue")
    response_date = fields.Datetime(string="Réponse reçue le")
    notes = fields.Text()
