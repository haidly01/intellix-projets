# -*- coding: utf-8 -*-
from odoo import fields, models


class VeilleConversationMessage(models.Model):
    _name = "doorway.veille.conversation.message"
    _description = "Message d'une conversation veille sociale"
    _order = "posted_at asc, id asc"

    signal_id = fields.Many2one(
        "doorway.veille.signal",
        string="Signal",
        required=True,
        ondelete="cascade",
        index=True,
    )
    direction = fields.Selection(
        [("inbound", "Reçu"), ("outbound", "Envoyé")],
        string="Direction",
        default="inbound",
        required=True,
    )
    author_name = fields.Char(string="Auteur")
    body = fields.Text(string="Message", required=True)
    external_id = fields.Char(string="ID externe", index=True, copy=False)
    posted_at = fields.Datetime(string="Publié le")
    platform = fields.Char(string="Plateforme")
