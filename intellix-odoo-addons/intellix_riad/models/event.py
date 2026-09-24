# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .event_template import CHECKLIST_KINDS, EVENT_KINDS, TEMPLATE_XMLIDS

MEAL_PLANS = [
    ("petit_dejeuner", "Petit-déjeuner"),
    ("demi_pension", "Demi-pension"),
    ("pension_complete", "Pension complète"),
    ("a_la_carte", "Restaurant à la carte"),
]

OCCUPIED = ("draft", "confirmed", "in_progress")


class IntellixRiadEvent(models.Model):
    _name = "intellix.riad.event"
    _description = "Dossier événement hébergement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start"

    name = fields.Char(string="Nom de l'événement", required=True, tracking=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
        default=lambda self: self.env.user.riad_establishment_ids[:1],
    )
    establishment_property_id = fields.Many2one(
        related="establishment_id.property_id",
        readonly=True,
    )
    partner_id = fields.Many2one("res.partner", string="Client", tracking=True)
    date_start = fields.Datetime(
        string="Début",
        required=True,
        tracking=True,
        default=fields.Datetime.now,
    )
    date_end = fields.Datetime(string="Fin")
    day_start = fields.Date(string="Date de début")
    day_end = fields.Date(string="Date de fin")
    guest_count = fields.Integer(string="Nombre de personnes")
    notes = fields.Text()
    event_kind = fields.Selection(EVENT_KINDS, string="Type")
    checklist_kind = fields.Selection(
        CHECKLIST_KINDS,
        string="Modèle de checklist",
        default="privatisation_weekend",
    )
    template_id = fields.Many2one(
        "intellix.riad.event.template",
        string="Modèle de checklist",
        tracking=True,
    )
    template_preview_html = fields.Html(
        string="Aperçu checklist",
        compute="_compute_template_preview",
    )
    meal_plan = fields.Selection(MEAL_PLANS, string="Formule restaurant")
    include_half_board = fields.Boolean(string="Formule demi-pension")
    include_group_wellness = fields.Boolean(string="Session bien-être groupe")
    is_full_privatisation = fields.Boolean(
        string="Privatisation complète du riad",
        help="Bloque toutes les chambres, le restaurant et le bien-être externe.",
    )
    referral_source = fields.Char(
        string="Source de référence",
        help="Code créateur ou lien de cross-promotion Coins Québec.",
    )
    room_ids = fields.Many2many(
        "coins.property.room",
        "intellix_riad_event_room_rel",
        "event_id",
        "room_id",
        string="Chambres concernées",
    )
    privatisation_id = fields.Many2one(
        "intellix.riad.privatisation",
        string="Privatisation",
        ondelete="set null",
    )
    conflict_html = fields.Html(string="Conflits", readonly=True)
    acknowledge_conflicts = fields.Boolean(
        string="J'ai lu les conflits : les réservations existantes ne seront pas écrasées",
    )
    reservation_ids = fields.Many2many(
        "coins.reservation",
        "intellix_riad_event_reservation_rel",
        "event_id",
        "reservation_id",
        string="Réservations chambres",
    )
    wellness_slot_ids = fields.Many2many(
        "intellix.riad.wellness.slot",
        "intellix_riad_event_slot_rel",
        "event_id",
        "slot_id",
        string="Créneaux bien-être",
    )
    table_ids = fields.Many2many(
        "intellix.riad.table",
        "intellix_riad_event_table_rel",
        "event_id",
        "table_id",
        string="Tables restaurant",
    )
    task_ids = fields.One2many(
        "intellix.riad.event.task",
        "event_id",
        string="Tâches",
    )
    task_done_count = fields.Integer(compute="_compute_task_progress")
    task_total_count = fields.Integer(compute="_compute_task_progress")
    task_progress_label = fields.Char(compute="_compute_task_progress")
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirmé"),
            ("in_progress", "En cours"),
            ("done", "Terminé"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        tracking=True,
    )

    @api.depends("task_ids.state")
    def _compute_task_progress(self):
        for rec in self:
            total = len(rec.task_ids)
            done = len(rec.task_ids.filtered(lambda t: t.state == "done"))
            rec.task_total_count = total
            rec.task_done_count = done
            rec.task_progress_label = "%s/%s" % (done, total) if total else "0/0"

    @api.depends("template_id", "template_id.line_ids", "template_id.line_ids.name")
    def _compute_template_preview(self):
        for rec in self:
            if not rec.template_id:
                rec.template_preview_html = False
                continue
            items = "".join(
                '<div class="o_riad_check_item">%s</div>' % (line.name or "")
                for line in rec.template_id.line_ids
            )
            rec.template_preview_html = (
                '<div class="o_riad_checklist_preview">%s</div>' % items
            )

    def _template_for_kind(self, kind):
        if not kind or kind == "none":
            return self.env["intellix.riad.event.template"]
        xmlid = TEMPLATE_XMLIDS.get(kind)
        template = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else False
        if template:
            return template
        return self.env["intellix.riad.event.template"].search(
            [("event_kind", "=", kind)], limit=1
        )

    def _sync_days_from_vals(self, vals):
        if vals.get("day_start") and not vals.get("date_start"):
            vals["date_start"] = fields.Datetime.to_datetime(vals["day_start"])
        if vals.get("day_end") and not vals.get("date_end"):
            vals["date_end"] = fields.Datetime.to_datetime(vals["day_end"]) + timedelta(
                hours=23, minutes=59
            )
        if vals.get("date_start") and "day_start" not in vals:
            start = fields.Datetime.to_datetime(vals["date_start"])
            vals["day_start"] = start.date() if start else False
        if vals.get("date_end") and "day_end" not in vals:
            end = fields.Datetime.to_datetime(vals["date_end"])
            vals["day_end"] = end.date() if end else False
        if vals.get("checklist_kind") and "template_id" not in vals:
            template = self._template_for_kind(vals["checklist_kind"])
            vals["template_id"] = template.id if template else False
            if vals["checklist_kind"] != "none":
                vals["event_kind"] = vals["checklist_kind"]
        if vals.get("include_half_board") and not vals.get("meal_plan"):
            vals["meal_plan"] = "demi_pension"

    @api.onchange("day_start", "day_end")
    def _onchange_days(self):
        for rec in self:
            if rec.day_start:
                rec.date_start = fields.Datetime.to_datetime(rec.day_start)
            if rec.day_end:
                rec.date_end = fields.Datetime.to_datetime(rec.day_end) + timedelta(
                    hours=23, minutes=59
                )

    @api.onchange("checklist_kind")
    def _onchange_checklist_kind(self):
        template = self._template_for_kind(self.checklist_kind)
        self.template_id = template
        self.event_kind = (
            self.checklist_kind
            if self.checklist_kind and self.checklist_kind != "none"
            else False
        )

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if self.template_id and not self.event_kind:
            self.event_kind = self.template_id.event_kind

    @api.onchange("is_full_privatisation", "establishment_id")
    def _onchange_privatisation_rooms(self):
        if self.is_full_privatisation and self.establishment_id:
            rooms = self.establishment_id.property_id.room_ids.filtered("active")
            self.room_ids = rooms
            if not self.checklist_kind or self.checklist_kind == "none":
                self.checklist_kind = "privatisation_weekend"
                self._onchange_checklist_kind()

    @api.onchange("include_half_board")
    def _onchange_half_board(self):
        if self.include_half_board:
            self.meal_plan = "demi_pension"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_days_from_vals(vals)
        records = super().create(vals_list)
        records.filtered("template_id").action_apply_template()
        return records

    def write(self, vals):
        self._sync_days_from_vals(vals)
        res = super().write(vals)
        if vals.get("template_id"):
            self.action_apply_template()
        return res

    def action_apply_template(self):
        Task = self.env["intellix.riad.event.task"]
        for event in self:
            if not event.template_id:
                continue
            existing = set(event.task_ids.mapped("name"))
            start = event.date_start.date() if event.date_start else False
            for line in event.template_id.line_ids:
                if line.name in existing:
                    continue
                deadline = False
                if start:
                    deadline = start - timedelta(days=line.offset_days or 0)
                Task.create(
                    {
                        "event_id": event.id,
                        "name": line.name,
                        "sequence": line.sequence,
                        "date_deadline": deadline,
                    }
                )
        return True

    def _privatisation_dates(self):
        self.ensure_one()
        start = self.day_start or (self.date_start.date() if self.date_start else False)
        end = self.day_end or (self.date_end.date() if self.date_end else start)
        return start, end

    def _confirm_privatisation(self):
        self.ensure_one()
        start, end = self._privatisation_dates()
        if not start or not end:
            raise UserError("Indiquez les dates de début et de fin avant de privatiser.")
        Privatisation = self.env["intellix.riad.privatisation"]
        priv = self.privatisation_id
        if not priv:
            priv = Privatisation.create(
                {
                    "name": self.name,
                    "establishment_id": self.establishment_id.id,
                    "partner_id": self.partner_id.id,
                    "date_start": start,
                    "date_end": end,
                    "guest_count": self.guest_count,
                    "event_id": self.id,
                    "notes": self.referral_source or "",
                }
            )
            self.privatisation_id = priv.id
        else:
            priv.write(
                {
                    "date_start": start,
                    "date_end": end,
                    "guest_count": self.guest_count,
                    "event_id": self.id,
                }
            )
        conflicts = priv.collect_conflicts()
        html = priv._conflicts_html(conflicts)
        priv.conflict_html = html
        self.conflict_html = html
        if conflicts and not self.acknowledge_conflicts:
            raise UserError(
                "Des réservations existent déjà sur cette période. "
                "Relisez les conflits et cochez la confirmation. "
                "Rien ne sera écrasé."
            )
        priv.action_confirm(
            acknowledge_conflicts=bool(conflicts and self.acknowledge_conflicts)
        )
        self.reservation_ids = [(6, 0, priv.reservation_ids.ids)]
        self.room_ids = [(6, 0, priv.reservation_ids.mapped("room_id").ids)]
        code = (self.referral_source or "").strip()
        if code and self.reservation_ids:
            self.reservation_ids.filtered(lambda r: not r.referral_code).write(
                {"referral_code": code}
            )

    def _hold_selected_rooms(self):
        self.ensure_one()
        if not self.room_ids:
            return
        start, end = self._privatisation_dates()
        if not start:
            return
        check_out = (end or start) + timedelta(days=1)
        Res = self.env["coins.reservation"]
        occupied = Res.search(
            [
                ("property_id", "=", self.establishment_id.property_id.id),
                ("state", "in", list(OCCUPIED)),
                ("check_in", "<", check_out),
                ("check_out", ">", start),
            ]
        ).mapped("room_id")
        created = self.env["coins.reservation"]
        for room in self.room_ids:
            if room in occupied:
                continue
            vals = {
                "property_id": self.establishment_id.property_id.id,
                "room_id": room.id,
                "check_in": start,
                "check_out": check_out,
                "source": "direct",
                "booking_channel": "backoffice",
                "client_nom": self.name,
                "voyageurs": self.guest_count or 1,
                "meal_breakfast": True,
            }
            if "meal_dinner" in Res._fields:
                vals["meal_dinner"] = bool(self.include_half_board)
            code = (self.referral_source or "").strip()
            if code and "referral_code" in Res._fields:
                vals["referral_code"] = code
            resa = Res.create(vals)
            if hasattr(resa, "action_confirm"):
                resa.action_confirm()
            created |= resa
        if created:
            self.reservation_ids = [(4, rid) for rid in created.ids]

    def action_confirm(self):
        for rec in self:
            if rec.state in ("confirmed", "in_progress", "done"):
                continue
            rec._onchange_days()
            if rec.include_half_board:
                rec.meal_plan = "demi_pension"
            if rec.is_full_privatisation:
                rec._confirm_privatisation()
            else:
                rec._hold_selected_rooms()
            rec.state = "confirmed"
            rec.message_post(body="Événement confirmé.")
        return True

    def action_start(self):
        self.filtered(lambda r: r.state == "confirmed").write({"state": "in_progress"})
        return True

    def action_done(self):
        self.filtered(lambda r: r.state in ("confirmed", "in_progress")).write(
            {"state": "done"}
        )
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                continue
            if rec.privatisation_id and rec.privatisation_id.state == "confirmed":
                rec.privatisation_id.action_cancel()
            rec.state = "cancelled"
        return True

    def action_open_task_kanban(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name or "Tâches",
            "res_model": "intellix.riad.event.task",
            "view_mode": "kanban,list,form",
            "domain": [("event_id", "=", self.id)],
            "context": {
                "default_event_id": self.id,
                "search_default_event": 1,
            },
        }
