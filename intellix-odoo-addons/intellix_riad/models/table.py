# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class IntellixRiadTable(models.Model):
    _name = "intellix.riad.table"
    _description = "Table / couverts terrasse"
    _order = "sequence, id"

    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Table", required=True)
    seats = fields.Integer(string="Couverts", default=2)
    zone = fields.Selection(
        [
            ("terrasse", "Terrasse"),
            ("patio", "Patio"),
            ("salon", "Salon"),
        ],
        string="Zone",
        default="terrasse",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    notes = fields.Char()
    booking_guest = fields.Char(string="Cliente ce soir")
    booking_covers = fields.Integer(string="Couverts ce soir")
    booking_date = fields.Date(string="Date de réservation")
    ticket_ids = fields.One2many(
        "intellix.riad.table.ticket",
        "table_id",
        string="Additions",
    )


class IntellixRiadTableTicket(models.Model):
    _name = "intellix.riad.table.ticket"
    _description = "Addition restaurant"
    _order = "date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    table_id = fields.Many2one(
        "intellix.riad.table",
        required=True,
        ondelete="restrict",
        index=True,
    )
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    guest_kind = fields.Selection(
        [
            ("resident", "Résidente"),
            ("externe", "Cliente extérieure"),
        ],
        required=True,
        default="externe",
    )
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Séjour",
        ondelete="set null",
        index=True,
    )
    guest_name = fields.Char(required=True)
    covers = fields.Integer(default=2)
    currency_id = fields.Many2one(
        related="establishment_id.property_id.currency_id",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Note (hors pourboire)",
        currency_field="currency_id",
    )
    tip_amount = fields.Monetary(
        string="Pourboire",
        currency_field="currency_id",
        help="Jamais mélangé à la note. Comptant pour le personnel, ou poussé en chambre.",
    )
    tip_mode = fields.Selection(
        [
            ("cash", "Comptant — personnel"),
            ("room", "En chambre"),
        ],
        default="cash",
        required=True,
    )
    charge_to_room = fields.Boolean(
        string="Pousser la note à la chambre",
        help="Différencie la résidente (folio chambre) de la cliente extérieure (règlement à table).",
    )
    state = fields.Selection(
        [
            ("draft", "Ouverte"),
            ("charged", "En chambre"),
            ("paid", "Réglée à table"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        required=True,
    )
    room_folio = fields.Monetary(
        string="Montant folio chambre",
        currency_field="currency_id",
        compute="_compute_room_folio",
    )

    @api.depends("table_id.name", "guest_name", "date")
    def _compute_name(self):
        for rec in self:
            bits = [rec.table_id.name or "", rec.guest_name or ""]
            if rec.date:
                bits.append(rec.date.strftime("%d/%m"))
            rec.name = " · ".join(part for part in bits if part) or "Addition"

    @api.depends("amount", "tip_amount", "tip_mode", "charge_to_room")
    def _compute_room_folio(self):
        for rec in self:
            total = rec.amount or 0.0
            if rec.charge_to_room and rec.tip_mode == "room":
                total += rec.tip_amount or 0.0
            rec.room_folio = total if rec.charge_to_room else 0.0

    def action_charge_to_room(self):
        for rec in self:
            if rec.guest_kind != "resident" or not rec.reservation_id:
                raise UserError(
                    "Seule une résidente liée à un séjour peut envoyer la note en chambre."
                )
            rec.charge_to_room = True
            if rec.tip_amount and rec.tip_mode != "room":
                rec.tip_mode = "room"
            rec.state = "charged"
            symbol = rec.currency_id.symbol or ""
            tip_bit = ""
            if rec.tip_amount and rec.tip_mode == "room":
                tip_bit = " · pourboire %s%s" % (int(round(rec.tip_amount)), symbol)
            rec.reservation_id.message_post(
                body="Addition restaurant %s : %s%s%s. Le pourboire n'est pas dans le tarif chambre."
                % (
                    rec.table_id.name or "",
                    int(round(rec.amount or 0)),
                    symbol,
                    tip_bit,
                )
            )
        return True
