# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySocialMessage(models.Model):
    _name = "doorway.social.message"
    _description = "Message inbox réseaux sociaux"
    _order = "create_date asc"

    conversation_id = fields.Many2one(
        "doorway.social.inbox",
        required=True,
        ondelete="cascade",
        index=True,
    )
    direction = fields.Selection(
        [("inbound", "Reçu"), ("outbound", "Envoyé")],
        required=True,
        default="inbound",
    )
    content = fields.Text(required=True)
    media_url = fields.Char("URL média")
    media_type = fields.Selection(
        [
            ("image", "Image"),
            ("video", "Vidéo"),
            ("audio", "Audio"),
            ("file", "Fichier"),
        ]
    )
    is_read = fields.Boolean(default=False)
    author_id = fields.Many2one("res.users", "Auteur (sortant)")
    external_msg_id = fields.Char("ID message plateforme", index=True)
