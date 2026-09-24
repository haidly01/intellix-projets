# -*- coding: utf-8 -*-
from odoo import fields, models


class AgentLibraryItem(models.Model):
    _name = "doorway.agent.library.item"
    _description = "Bibliothèque de contenu agent IA"
    _order = "sequence, id"

    agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Titre", required=True)
    item_type = fields.Selection(
        [
            ("faq", "FAQ"),
            ("script", "Script"),
            ("objection", "Gestion objections"),
            ("offer", "Offre / produit"),
            ("policy", "Politique"),
        ],
        string="Type",
        default="faq",
        required=True,
    )
    language = fields.Selection(
        [("fr", "Français"), ("en", "Anglais"), ("bilingual", "Bilingue")],
        string="Langue",
        default="fr",
    )
    content = fields.Text(string="Contenu", required=True)
    active = fields.Boolean(default=True)
