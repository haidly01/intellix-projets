# -*- coding: utf-8 -*-
from odoo import fields, models

from .channel_config import CANAL_SELECTION


class DoorwayMessageLog(models.Model):
    _name = "doorway.message.log"
    _description = "Log envoi unitaire"
    _order = "date_envoi desc, id desc"

    campaign_id = fields.Many2one(
        "doorway.message.campaign", ondelete="cascade", index=True
    )
    canal = fields.Selection(CANAL_SELECTION, string="Canal", required=True)
    destinataire = fields.Char("Destinataire (email/tél/URN)")
    lead_id = fields.Many2one("crm.lead", ondelete="set null")
    partner_id = fields.Many2one("res.partner", ondelete="set null")

    statut = fields.Selection(
        [
            ("en_attente", "En attente"),
            ("envoye", "Envoyé"),
            ("lu", "Lu / Ouvert"),
            ("erreur", "Erreur"),
            ("refuse", "Refusé / Bounce"),
        ],
        default="en_attente",
        index=True,
    )

    date_envoi = fields.Datetime()
    date_lecture = fields.Datetime()
    message_id = fields.Char("ID message externe")
    erreur_msg = fields.Text("Message d'erreur")
    corps_envoye = fields.Text("Corps exact envoyé", readonly=True)
