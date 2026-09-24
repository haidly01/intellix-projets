# -*- coding: utf-8 -*-
"""RDV partenaires Réno Immobilier — table dédiée, pas coins.quebec.*."""
from odoo import api, fields, models

from .reno_rdv_tz import (
    RENO_MARTIN_LOGIN,
    reno_format_canada_short,
)


class RenovationPartnerRdv(models.Model):
    _name = "renovation.partner.rdv"
    _description = "RDV partenaire Réno Immobilier (Martin)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_at desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire Réno Immobilier",
        index=True,
        ondelete="set null",
        tracking=True,
    )
    lead_id = fields.Many2one(
        "crm.lead",
        string="Fiche lead (optionnel)",
        index=True,
        ondelete="cascade",
        tracking=True,
        help="Ancien lien CRM lead — le CRM partenaires utilise partner_id.",
    )
    booker_id = fields.Many2one(
        "res.users",
        string="Booké par",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    martin_user_id = fields.Many2one(
        "res.users",
        string="Hôte calendrier",
        required=True,
        index=True,
        tracking=True,
        help="Toujours Martin Houle — le RDV va sur son agenda.",
    )
    start_at = fields.Datetime(
        string="Début (UTC)",
        required=True,
        index=True,
        tracking=True,
    )
    stop_at = fields.Datetime(
        string="Fin (UTC)",
        required=True,
    )
    start_at_display = fields.Char(
        string="Créneau (heure du Canada)",
        compute="_compute_start_at_display",
    )
    event_id = fields.Many2one(
        "calendar.event",
        string="Événement calendrier",
        copy=False,
        ondelete="set null",
        index=True,
    )
    note = fields.Text(string="Note pour Martin")
    state = fields.Selection(
        [
            ("booked", "Booké"),
            ("done", "Effectué"),
            ("cancel", "Annulé"),
        ],
        string="Statut",
        default="booked",
        required=True,
        index=True,
        tracking=True,
    )
    event_tz = fields.Char(
        string="Fuseau du RDV",
        default=lambda self: "America/Toronto",
        required=True,
    )

    @api.model
    def _reno_martin_user(self):
        Users = self.env["res.users"].sudo()
        martin = Users.search([("login", "=", RENO_MARTIN_LOGIN)], limit=1)
        if martin:
            return martin
        fallback = Users.browse(10).exists()
        if fallback and "martin" in (fallback.name or "").lower():
            return fallback
        return Users.browse()

    @api.depends("partner_id", "lead_id", "booker_id", "start_at")
    def _compute_name(self):
        for rec in self:
            who = (
                rec.partner_id.name
                or (rec.lead_id.name if rec.lead_id else "")
                or "Prospect Réno"
            )
            booker = rec.booker_id.name or "?"
            rec.name = "RDV Réno — %s — %s" % (who, booker)

    @api.depends("start_at")
    def _compute_start_at_display(self):
        for rec in self:
            rec.start_at_display = reno_format_canada_short(rec.start_at) or False
