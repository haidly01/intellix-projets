# -*- coding: utf-8 -*-
from odoo import fields, models


class ItexLeadDocument(models.Model):
    _name = "itex.lead.document"
    _description = "Document d'adhésion ITEX"
    _order = "id"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Lead ITEX",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Document", required=True)
    status = fields.Selection(
        [
            ("attendu", "Attendu"),
            ("recu", "Reçu"),
            ("manquant", "Manquant"),
        ],
        string="Statut",
        default="attendu",
        required=True,
        index=True,
    )
