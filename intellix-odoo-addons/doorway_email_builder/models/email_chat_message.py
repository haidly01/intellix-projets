# -*- coding: utf-8 -*-
from odoo import fields, models


class EmailChatMessage(models.Model):
    _name = "doorway.email.chat.message"
    _description = "Message de chat — Email Builder IA"
    _order = "id asc"

    brief_id = fields.Many2one(
        "doorway.email.brief",
        string="Brief",
        required=True,
        ondelete="cascade",
        index=True,
    )
    role = fields.Selection(
        [
            ("user", "Utilisateur"),
            ("assistant", "Assistant"),
            ("system", "Système"),
        ],
        string="Rôle",
        required=True,
        default="user",
    )
    content = fields.Text(string="Message", required=True)

    def to_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content or "",
            "date": fields.Datetime.to_string(self.create_date) if self.create_date else "",
        }
