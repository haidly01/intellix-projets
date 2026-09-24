# -*- coding: utf-8 -*-
from odoo import fields, models


class SeoChatMessage(models.Model):
    _name = "doorway.seo.chat.message"
    _description = "Message de chat — SEO IA"
    _order = "id asc"

    workspace_id = fields.Many2one(
        "doorway.seo.workspace",
        string="Espace SEO",
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
