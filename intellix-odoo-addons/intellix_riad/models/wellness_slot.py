# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IntellixRiadWellnessSlot(models.Model):
    _name = "intellix.riad.wellness.slot"
    _description = "Créneau bien-être / beauté"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start"
    _rec_name = "name"

    name = fields.Char(compute="_compute_name", store=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    practitioner_id = fields.Many2one(
        "intellix.riad.practitioner",
        string="Prestataire",
        required=True,
        ondelete="restrict",
        index=True,
    )
    type_id = fields.Many2one(
        "intellix.riad.wellness.type",
        string="Soin",
        required=True,
    )
    date_start = fields.Datetime(string="Début", required=True)
    date_end = fields.Datetime(string="Fin")
    guest_kind = fields.Selection(
        [
            ("resident", "Résidente"),
            ("externe", "Externe"),
        ],
        string="Origine",
        required=True,
        default="resident",
    )
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation chambre",
        ondelete="set null",
    )
    guest_name = fields.Char(string="Nom affiché")
    experience_brief = fields.Text(
        string="Brief expérience",
        help="Brief pour le Créateur d'Expérience (un seul agent, bien-être + messages).",
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("booked", "Réservé"),
            ("done", "Terminé"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        related="establishment_id.property_id.currency_id",
        readonly=True,
    )
    amount = fields.Monetary(string="Montant", currency_field="currency_id")
    establishment_property_id = fields.Many2one(
        related="establishment_id.property_id",
        readonly=True,
    )
    stay_room_id = fields.Many2one(
        related="reservation_id.room_id",
        string="Chambre du séjour",
        readonly=True,
    )
    stay_check_in = fields.Date(
        related="reservation_id.check_in",
        string="Arrivée (séjour)",
        readonly=True,
    )
    stay_check_out = fields.Date(
        related="reservation_id.check_out",
        string="Départ (séjour)",
        readonly=True,
    )
    stay_nights = fields.Integer(
        related="reservation_id.nights",
        string="Nuits",
        readonly=True,
    )

    @api.depends("type_id", "guest_name", "date_start", "state")
    def _compute_name(self):
        for rec in self:
            who = rec.guest_name or _("Nouvelle cliente")
            soin = rec.type_id.name or _("Créneau bien-être")
            when = rec.date_start.strftime("%d/%m %Hh%M") if rec.date_start else _("Nouveau")
            rec.name = "%s — %s — %s" % (soin, who, when)

    def _assert_external_allowed(self):
        Privatisation = self.env["intellix.riad.privatisation"]
        for rec in self:
            if rec.guest_kind != "externe" or rec.state == "cancelled":
                continue
            if not rec.establishment_id or not rec.date_start:
                continue
            day = rec.date_start.date()
            if Privatisation.is_active_on(rec.establishment_id, day):
                raise UserError(
                    _(
                        "Privatisation en cours : aucune cliente externe ne peut "
                        "réserver un soin (massage, hammam, esthétique, brushing). "
                        "Les résidentes du groupe restent prioritaires."
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._assert_external_allowed()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("guest_kind", "date_start", "state", "establishment_id")):
            self._assert_external_allowed()
        return res

    @api.onchange("reservation_id", "guest_kind")
    def _onchange_guest_name(self):
        for rec in self:
            if rec.guest_kind == "resident" and rec.reservation_id:
                rec.guest_name = (
                    rec.reservation_id.client_nom
                    or rec.reservation_id.traveler_id.name
                    or rec.reservation_id.room_id.name
                )

    def action_confirm(self):
        self.write({"state": "booked"})
        return True

    def action_mark_done(self):
        self.write({"state": "done"})
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True
