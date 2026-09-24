# -*- coding: utf-8 -*-
from odoo import api, fields, models


CHECKLIST = (
    ("call_validation", "Appel — valider l'expérience"),
    ("transfert", "Transfert aéroport / gare"),
    ("voiture", "Location de voiture"),
    ("restaurant", "Restaurant"),
    ("activite", "Activité / excursion"),
    ("evenement", "Événement / soirée"),
    ("soin", "Soin / hammam"),
)


class CoinsConciergeLine(models.Model):
    _name = "coins.concierge.line"
    _description = "Ligne dossier conciergerie"
    _order = "sequence, id"

    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    line_type = fields.Selection(list(CHECKLIST), string="Poste", required=True)
    name = fields.Char(string="Libellé", required=True)
    state = fields.Selection(
        [
            ("todo", "À faire"),
            ("proposed", "Proposé"),
            ("validated", "Validé client"),
            ("booked", "Booké prestataire"),
            ("cancelled", "Annulé"),
        ],
        string="Statut",
        default="todo",
        required=True,
    )
    scheduled_at = fields.Datetime(string="Créneau")
    partner_note = fields.Char(string="Prestataire / note")
    notes = fields.Text(string="Détail")

    @api.model
    def _seed_for_reservation(self, reservation):
        if reservation.concierge_line_ids:
            return reservation.concierge_line_ids
        seq = 10
        lines = []
        for code, label in CHECKLIST:
            lines.append(
                {
                    "reservation_id": reservation.id,
                    "sequence": seq,
                    "line_type": code,
                    "name": label,
                    "state": "todo",
                }
            )
            seq += 10
        return self.create(lines)
