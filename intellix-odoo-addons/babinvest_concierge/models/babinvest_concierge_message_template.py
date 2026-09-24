# -*- coding: utf-8 -*-

from odoo import fields, models


class BabinvestConciergeMessageTemplate(models.Model):
    _name = "babinvest.concierge.message.template"
    _description = "Gabarit de relance (persona × étape) — conciergerie Bab Invest"
    _order = "persona, sequence"

    name = fields.Char(string="Libellé", required=True)
    sequence = fields.Integer(default=10)
    persona = fields.Selection(
        [
            ("locatif_pur", "Locatif pur"),
            ("residence_secondaire", "Résidence secondaire"),
            ("retraite_etranger", "Retraite à l'étranger"),
            ("mre", "MRE (Marocain résident à l'étranger)"),
            ("investisseur_multi_lots", "Investisseur multi-lots"),
        ],
        required=True,
    )
    step_label = fields.Char(
        string="Étape / délai", required=True, help="Ex. « Qualification (J+0) », « Relance J+3 »."
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
    content = fields.Text(
        string="Contenu",
        required=True,
        help="Variables entre {{ }} à mapper depuis le lead par n8n avant l'envoi.",
    )
