# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPropertyOpsSlot(models.Model):
    _name = "coins.property.ops.slot"
    _description = "Créneau ops bien (daypass / repas / check-in)"
    _order = "date_start, id"

    property_id = fields.Many2one(
        "coins.property",
        string="Bien",
        required=True,
        ondelete="cascade",
        index=True,
    )
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        ondelete="cascade",
        index=True,
    )
    slot_type = fields.Selection(
        [
            ("daypass", "Daypass piscine"),
            ("breakfast", "Petit-déjeuner"),
            ("lunch", "Déjeuner"),
            ("dinner", "Dîner"),
            ("check_in", "Check-in"),
        ],
        string="Type",
        required=True,
        index=True,
    )
    name = fields.Char(string="Libellé", required=True)
    date_start = fields.Datetime(string="Début", required=True)
    date_end = fields.Datetime(string="Fin")
    notes = fields.Text(string="Notes")
    state = fields.Selection(
        [
            ("planned", "Planifié"),
            ("done", "Fait"),
            ("cancelled", "Annulé"),
        ],
        string="Statut",
        default="planned",
        required=True,
    )
