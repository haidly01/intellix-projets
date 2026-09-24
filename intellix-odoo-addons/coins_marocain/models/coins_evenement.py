# -*- coding: utf-8 -*-
from datetime import timedelta
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoinsEvenement(models.Model):
    _name = "coins.evenement"
    _description = "Événement Coins Marocain"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    _CALENDAR_SYNC_STATES = (
        "confirmed",
        "deposit_received",
        "day_j",
        "done",
        "invoiced",
    )

    name = fields.Char(string="Nom de l'événement", required=True, tracking=True)
    reference = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Nouveau"),
    )
    active = fields.Boolean(default=True)
    event_type = fields.Selection(
        [
            ("pilote", "Pilote"),
            ("mariage", "Mariage"),
            ("soiree_recurrente", "Soirée récurrente"),
            ("privatisation", "Privatisation"),
            ("other", "Autre"),
        ],
        string="Type",
        default="pilote",
        required=True,
        tracking=True,
    )
    date_start = fields.Datetime(string="Début", required=True, tracking=True)
    date_end = fields.Datetime(string="Fin", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("quote_sent", "Devis envoyé"),
            ("confirmed", "Confirmé"),
            ("deposit_received", "Acompte reçu"),
            ("day_j", "Jour-J"),
            ("done", "Terminé"),
            ("invoiced", "Facturé / Soldé"),
            ("cancelled", "Annulé"),
        ],
        string="Statut",
        default="draft",
        required=True,
        tracking=True,
    )
    property_id = fields.Many2one(
        "coins.property",
        string="Lieu",
        tracking=True,
        help="Bien / rooftop / villa — type « Événements / rooftop » recommandé.",
    )
    partner_activity_id = fields.Many2one(
        "coins.partner_activity",
        string="Lieu (partenaire activité)",
        ondelete="set null",
    )
    capacity_planned = fields.Integer(string="Capacité prévue", default=0, tracking=True)
    audience_target = fields.Char(string="Public cible")
    internal_notes = fields.Text(string="Notes internes")
    ticketing_enabled = fields.Boolean(string="Billetterie activée", default=False)
    ticket_price = fields.Monetary(
        string="Prix du billet", currency_field="currency_id", default=0
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        default=lambda self: self.env.company.currency_id.id,
    )
    prestataire_ids = fields.One2many(
        "coins.evenement.prestataire", "evenement_id", string="Prestataires"
    )
    invite_ids = fields.One2many(
        "coins.evenement.invite", "evenement_id", string="Invités / RSVP"
    )
    total_cost = fields.Monetary(
        string="Coût total",
        currency_field="currency_id",
        compute="_compute_financials",
        store=True,
    )
    total_revenue = fields.Monetary(
        string="Revenu total",
        currency_field="currency_id",
        compute="_compute_financials",
        store=True,
    )
    profit_loss = fields.Monetary(
        string="Profit / Perte",
        currency_field="currency_id",
        compute="_compute_financials",
        store=True,
    )
    breakeven_tickets = fields.Float(
        string="Seuil billets (rentabilité)",
        compute="_compute_financials",
        store=True,
    )
    invite_confirmed_count = fields.Integer(
        string="Confirmés"
    )
    invite_present_count = fields.Integer(
        string="Présents"
    )
    payment_status = fields.Selection(
        [
            ("unpaid", "Non payé"),
            ("partial", "Partiel / acompte"),
            ("paid", "Payé"),
        ],
        string="Statut paiement",
        default="unpaid",
        tracking=True,
    )
    calendar_event_id = fields.Many2one(
        "calendar.event", string="Événement calendrier", copy=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", _("Nouveau")) == _("Nouveau"):
                seq = self.env["ir.sequence"].next_by_code("coins.evenement")
                vals["reference"] = seq or _("Nouveau")
        records = super().create(vals_list)
        records._sync_calendar_event()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("state", "date_start", "date_end", "name")):
            self._sync_calendar_event()
        if "state" in vals:
            closing = self.filtered(lambda r: r.state in r._CALENDAR_SYNC_STATES)
            closing._close_property_otas()
            cancelled = self.filtered(lambda r: r.state == "cancelled")
            cancelled._release_property_otas()
        elif {"date_start", "date_end", "property_id"} & set(vals):
            self.filtered(lambda r: r.state in r._CALENDAR_SYNC_STATES)._close_property_otas()
        return res

    @api.depends(
        "prestataire_ids.cost_actual",
        "prestataire_ids.cost_planned",
        "ticketing_enabled",
        "ticket_price",
        "invite_ids.ticket_amount",
        "invite_ids.payment_status",
    )
    def _compute_financials(self):
        for rec in self:
            cost = sum(
                (line.cost_actual or line.cost_planned or 0.0)
                for line in rec.prestataire_ids
            )
            revenue = 0.0
            if rec.ticketing_enabled:
                revenue = sum(
                    (inv.ticket_amount or 0.0)
                    for inv in rec.invite_ids
                    if inv.payment_status in ("paid", "partial")
                )
            rec.total_cost = cost
            rec.total_revenue = revenue
            rec.profit_loss = revenue - cost
            if rec.ticketing_enabled and rec.ticket_price and rec.ticket_price > 0:
                rec.breakeven_tickets = cost / rec.ticket_price
            else:
                rec.breakeven_tickets = 0.0

    @api.depends("invite_ids.rsvp_state")
    def _compute_invite_stats(self):
        for rec in self:
            rec.invite_confirmed_count = len(
                rec.invite_ids.filtered(lambda i: i.rsvp_state == "confirmed")
            )
            rec.invite_present_count = len(
                rec.invite_ids.filtered(lambda i: i.rsvp_state == "present")
            )

    def action_send_quote(self):
        self.write({"state": "quote_sent"})

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def _event_date_range(self):
        self.ensure_one()
        if not self.date_start:
            return False, False
        date_from = self.date_start.date()
        date_to = self.date_end.date() if self.date_end else date_from
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        return date_from, date_to

    def _close_property_otas(self):
        """Événement Coins = priorité 1 : calendrier local + file fermeture OTA."""
        for rec in self:
            if not rec.property_id or not rec.date_start:
                continue
            date_from, date_to = rec._event_date_range()
            rec.property_id._close_otas(
                date_from,
                date_to,
                "evenement",
                rec.reference or rec.name or "",
                source="evenement",
                extra={"evenement_id": rec.id},
            )

    def _release_property_otas(self):
        Blocage = self.env["coins.property.blocage"]
        for rec in self:
            blocks = Blocage.search(
                [("evenement_id", "=", rec.id), ("statut", "=", "confirme")]
            )
            if blocks:
                blocks.write({"statut": "annule"})
            if not rec.property_id or not rec.date_start:
                continue
            date_from, date_to = rec._event_date_range()
            rec.property_id._release_otas_if_free(
                date_from, date_to, origin=rec.reference or rec.name or ""
            )

    def action_deposit_received(self):
        self.write({"state": "deposit_received", "payment_status": "partial"})

    def action_day_j(self):
        self.write({"state": "day_j"})

    def action_done(self):
        self.write({"state": "done"})

    def action_invoiced(self):
        self.write({"state": "invoiced", "payment_status": "paid"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_open_calendar_event(self):
        self.ensure_one()
        if not self.calendar_event_id:
            raise UserError(_("Aucun événement calendrier lié."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "calendar.event",
            "view_mode": "form",
            "res_id": self.calendar_event_id.id,
        }

    def _prepare_calendar_event_vals(self):
        self.ensure_one()
        start = self.date_start
        stop = self.date_end or (self.date_start + timedelta(hours=4) if self.date_start else False)
        place = (
            self.property_id.display_name
            or self.partner_activity_id.name
            or ""
        )
        return {
            "name": self.name,
            "start": start,
            "stop": stop,
            "description": place,
            "location": place,
        }

    def _sync_calendar_event(self):
        Event = self.env["calendar.event"].sudo()
        for rec in self:
            if rec.state == "cancelled" or rec.state not in rec._CALENDAR_SYNC_STATES:
                if rec.calendar_event_id:
                    rec.calendar_event_id.sudo().write({"active": False})
                continue
            vals = rec._prepare_calendar_event_vals()
            if rec.calendar_event_id:
                rec.calendar_event_id.sudo().write(vals)
            else:
                rec.calendar_event_id = Event.create(vals).id

    @api.model
    def _cron_j1_reminders(self):
        from odoo.addons.coins_marocain.services.evenement_service import (
            CoinsEvenementService,
        )

        return CoinsEvenementService(self.env).notify_j1_reminders()

    @api.model
    def _cron_prestataire_quote_relance(self):
        from odoo.addons.coins_marocain.services.evenement_service import (
            CoinsEvenementService,
        )

        return CoinsEvenementService(self.env).notify_prestataire_quote_overdue()
