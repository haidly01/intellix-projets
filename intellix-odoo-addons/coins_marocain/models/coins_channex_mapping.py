# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsChannexMapping(models.Model):
    _name = "coins.channex.mapping"
    _description = "Correspondance IntelliX ↔ Channex"
    _order = "kind, local_id"

    kind = fields.Selection(
        [
            ("property", "Bien"),
            ("room_type", "Type de chambre"),
            ("rate_plan", "Plan tarifaire"),
            ("booking", "Réservation OTA"),
        ],
        string="Type",
        required=True,
        index=True,
    )
    local_id = fields.Integer(string="ID local", required=True, index=True)
    channex_id = fields.Char(string="UUID Channex", required=True, index=True)
    property_id = fields.Many2one("coins.property", string="Bien", ondelete="cascade")
    note = fields.Char(string="Note")

    _sql_constraints = [
        (
            "kind_local_uniq",
            "unique(kind, local_id)",
            "Ce mapping local existe déjà.",
        ),
    ]
