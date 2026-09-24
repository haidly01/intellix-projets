# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoinsQuebecReservation(models.Model):
    _name = "coins.quebec.reservation"
    _description = "Réservation (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "check_in desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: _("Nouveau"),
    )
    active = fields.Boolean(default=True)
    traveler_id = fields.Many2one("res.partner", string="Voyageur", required=True)
    lead_id = fields.Many2one("crm.lead", string="Fiche voyageur", ondelete="set null")
    property_id = fields.Many2one(
        "coins.quebec.property", string="Bien réservé", required=True, tracking=True
    )
    partner_activity_ids = fields.Many2many(
        "coins.quebec.partner.activity", string="Activités"
    )
    driver_id = fields.Many2one("coins.quebec.driver", string="Chauffeur")
    check_in = fields.Date(string="Arrivée", required=True, tracking=True)
    check_out = fields.Date(string="Départ", required=True, tracking=True)
    nights = fields.Integer(compute="_compute_nights", store=True)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirmée"),
            ("in_progress", "En cours"),
            ("done", "Terminée"),
            ("cancelled", "Annulée"),
        ],
        string="Statut",
        default="draft",
        required=True,
        tracking=True,
    )
    source = fields.Selection(
        [
            ("direct", "Direct"),
            ("referral", "Parrainage"),
            ("booking", "Booking.com"),
            ("airbnb", "Airbnb"),
            ("expedia", "Expedia"),
            ("channex", "OTA (Channex)"),
            ("ads", "Publicité"),
        ],
        default="direct",
    )
    referral_code = fields.Char(string="Code parrainage")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id, required=True
    )
    amount_property = fields.Monetary(string="Montant bien", currency_field="currency_id")
    amount_activities = fields.Monetary(
        string="Montant activités", currency_field="currency_id"
    )
    amount_transport = fields.Monetary(
        string="Montant transport", currency_field="currency_id"
    )
    amount_tax = fields.Monetary(
        string="TPS / TVQ",
        currency_field="currency_id",
        help="Taxes québécoises (TPS 5 % + TVQ 9,975 %).",
    )
    amount_total = fields.Monetary(
        string="Total TTC",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )
    payment_status = fields.Selection(
        [("unpaid", "Non payé"), ("partial", "Partiel"), ("paid", "Payé")],
        default="unpaid",
        tracking=True,
    )
    notes = fields.Text()
    is_demo = fields.Boolean(
        string="Réservation démo Mon Coin",
        default=False,
        index=True,
        copy=False,
    )
    line_ids = fields.One2many(
        "coins.quebec.reservation.line", "reservation_id", string="Lignes"
    )

    @api.depends("check_in", "check_out")
    def _compute_nights(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                rec.nights = max((rec.check_out - rec.check_in).days, 0)
            else:
                rec.nights = 0

    @api.depends("amount_property", "amount_activities", "amount_transport", "amount_tax")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = (
                (rec.amount_property or 0)
                + (rec.amount_activities or 0)
                + (rec.amount_transport or 0)
                + (rec.amount_tax or 0)
            )

    @api.onchange(
        "amount_property", "amount_activities", "amount_transport"
    )
    def _onchange_compute_tax(self):
        ht = (
            (self.amount_property or 0)
            + (self.amount_activities or 0)
            + (self.amount_transport or 0)
        )
        self.amount_tax = round(ht * 0.14975, 2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("Nouveau"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "coins.quebec.reservation"
                ) or _("CQ-RES")
            if (vals.get("name") or "").strip() == "CQ-RES/2026/0001":
                vals["is_demo"] = False
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("mon_coin_demo"):
            protected = self.filtered(
                lambda r: (r.name or "").strip() == "CQ-RES/2026/0001" or not r.is_demo
            )
            if protected:
                raise UserError(
                    _("Mode démo : écriture interdite sur une réservation réelle.")
                )
        return super().write(vals)

    def unlink(self):
        blocked = self.filtered(
            lambda r: (r.name or "").strip() == "CQ-RES/2026/0001"
        )
        if blocked:
            raise UserError(
                _("La réservation CQ-RES/2026/0001 est protégée et ne peut pas être supprimée.")
            )
        return super().unlink()


class CoinsQuebecReservationLine(models.Model):
    _name = "coins.quebec.reservation.line"
    _description = "Ligne de réservation (Coins Québec)"
    _inherit = ["coins.quebec.cad.mixin"]

    reservation_id = fields.Many2one(
        "coins.quebec.reservation", required=True, ondelete="cascade"
    )
    name = fields.Char(string="Description", required=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    amount = fields.Monetary(currency_field="currency_id")
