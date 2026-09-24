# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

OCCUPIED = ("draft", "confirmed", "in_progress")


class IntellixRiadPrivatisation(models.Model):
    _name = "intellix.riad.privatisation"
    _description = "Privatisation complète du riad"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(string="Groupe / intitulé", required=True, tracking=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one("res.partner", string="Client")
    date_start = fields.Date(string="Début", required=True, tracking=True)
    date_end = fields.Date(
        string="Fin (dernière nuit)",
        required=True,
        tracking=True,
        help="Dernière nuit bloquée. Les ressources redeviennent libres le lendemain.",
    )
    guest_count = fields.Integer(string="Personnes")
    notes = fields.Text()
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirmée"),
            ("done", "Terminée"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        tracking=True,
    )
    conflict_html = fields.Html(string="Conflits", readonly=True)
    has_conflicts = fields.Boolean(compute="_compute_has_conflicts")
    reservation_ids = fields.One2many(
        "coins.reservation",
        "riad_privatisation_id",
        string="Chambres bloquées",
    )
    event_id = fields.Many2one("intellix.riad.event", string="Dossier événement")
    channex_closed = fields.Boolean(string="Fermeture Channex envoyée", readonly=True)

    @api.depends("conflict_html")
    def _compute_has_conflicts(self):
        for rec in self:
            rec.has_conflicts = bool(rec.conflict_html)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError("La fin de privatisation doit être après le début.")

    def check_out_date(self):
        self.ensure_one()
        return self.date_end + timedelta(days=1)

    @api.model
    def search_active(self, establishment, day_from, day_to=None):
        day_to = day_to or day_from
        return self.search(
            [
                ("establishment_id", "=", establishment.id),
                ("state", "=", "confirmed"),
                ("date_start", "<=", day_to),
                ("date_end", ">=", day_from),
            ]
        )

    @api.model
    def is_active_on(self, establishment, day):
        return bool(self.search_active(establishment, day, day))

    def collect_conflicts(self):
        self.ensure_one()
        return self._collect_conflicts(
            self.establishment_id, self.date_start, self.date_end, exclude_id=self.id
        )

    @api.model
    def _collect_conflicts(self, establishment, date_start, date_end, exclude_id=None):
        if not establishment or not date_start or not date_end:
            return []
        check_out = date_end + timedelta(days=1)
        rows = []
        domain = [
            ("property_id", "=", establishment.property_id.id),
            ("state", "in", list(OCCUPIED)),
            ("check_in", "<", check_out),
            ("check_out", ">", date_start),
        ]
        if exclude_id:
            domain.append(("riad_privatisation_id", "!=", exclude_id))
        else:
            domain.append(("riad_privatisation_id", "=", False))
        for resa in self.env["coins.reservation"].search(domain, order="check_in, room_id"):
            room = resa.room_id.name or "Chambre"
            guest = resa.client_nom or resa.name or "—"
            rows.append(
                {
                    "kind": "chambre",
                    "label": "%s — %s (%s → %s)"
                    % (room, guest, resa.check_in, resa.check_out),
                }
            )
        slots = self.env["intellix.riad.wellness.slot"].search(
            [
                ("establishment_id", "=", establishment.id),
                ("guest_kind", "=", "externe"),
                ("state", "in", ("draft", "booked")),
                ("date_start", "<", fields.Datetime.to_datetime(check_out)),
                ("date_start", ">=", fields.Datetime.to_datetime(date_start)),
            ]
        )
        for slot in slots:
            when = slot.date_start.strftime("%d/%m %Hh%M") if slot.date_start else ""
            rows.append(
                {
                    "kind": "bien-être",
                    "label": "%s — %s (%s, externe)"
                    % (slot.type_id.name or "Soin", slot.guest_name or "Cliente", when),
                }
            )
        others = self.search(
            [
                ("establishment_id", "=", establishment.id),
                ("state", "=", "confirmed"),
                ("date_start", "<=", date_end),
                ("date_end", ">=", date_start),
                ("id", "!=", exclude_id or 0),
            ]
        )
        for other in others:
            rows.append(
                {
                    "kind": "privatisation",
                    "label": "Déjà privatisé : %s (%s → %s)"
                    % (other.name, other.date_start, other.date_end),
                }
            )
        return rows

    def _conflicts_html(self, rows):
        if not rows:
            return False
        lines = [
            "<p><b>Des réservations existent déjà sur cette période. "
            "Elles ne seront pas écrasées.</b></p><ul>"
        ]
        for row in rows:
            lines.append("<li>[%s] %s</li>" % (row["kind"], row["label"]))
        lines.append("</ul>")
        return "".join(lines)

    def action_refresh_conflicts(self):
        for rec in self:
            rec.conflict_html = rec._conflicts_html(rec.collect_conflicts())
        return True

    def _create_room_holds(self):
        self.ensure_one()
        Res = self.env["coins.reservation"]
        check_out = self.check_out_date()
        occupied_rooms = Res.search(
            [
                ("property_id", "=", self.establishment_id.property_id.id),
                ("state", "in", list(OCCUPIED)),
                ("check_in", "<", check_out),
                ("check_out", ">", self.date_start),
            ]
        ).mapped("room_id")
        created = self.env["coins.reservation"]
        for room in self.establishment_id.property_id.room_ids.filtered("active"):
            if room in occupied_rooms:
                continue
            vals = {
                "property_id": self.establishment_id.property_id.id,
                "room_id": room.id,
                "check_in": self.date_start,
                "check_out": check_out,
                "source": "direct",
                "booking_channel": "backoffice",
                "client_nom": "Privatisation — %s" % self.name,
                "voyageurs": self.guest_count or 1,
                "meal_breakfast": True,
                "riad_privatisation_id": self.id,
            }
            code = (
                self.event_id.referral_source if self.event_id else ""
            ) or ""
            if code.strip() and "referral_code" in Res._fields:
                vals["referral_code"] = code.strip()
            resa = Res.with_context(riad_skip_close_otas=True).create(vals)
            if hasattr(resa, "action_confirm"):
                resa.with_context(riad_skip_close_otas=True).action_confirm()
            else:
                resa.write({"state": "confirmed"})
            created |= resa
        return created

    def _close_channex(self):
        self.ensure_one()
        prop = self.establishment_id.property_id
        if not prop:
            return
        prop._close_otas(
            self.date_start,
            self.date_end,
            "evenement",
            origin="Privatisation #%s — %s" % (self.id, self.name),
            source="direct",
        )
        Push = self.env["coins.channex.push"]
        if hasattr(Push, "cron_flush"):
            Push.cron_flush()
        self.channex_closed = True

    def _release_channex(self):
        self.ensure_one()
        prop = self.establishment_id.property_id
        if not prop:
            return
        origin = "Privatisation #%s" % self.id
        blocks = self.env["coins.property.blocage"].search(
            [
                ("property_id", "=", prop.id),
                ("date_debut", "=", self.date_start),
                ("date_fin", "=", self.date_end),
                ("statut", "=", "confirme"),
                ("summary", "ilike", origin),
            ]
        )
        if blocks:
            blocks.write({"statut": "annule"})
        if hasattr(prop, "_release_otas_if_free"):
            prop._release_otas_if_free(
                self.date_start, self.date_end, origin="fin privatisation #%s" % self.id
            )
        Push = self.env["coins.channex.push"]
        if hasattr(Push, "cron_flush"):
            Push.cron_flush()

    def _ensure_event(self):
        self.ensure_one()
        if self.event_id:
            return self.event_id
        template = self.env["intellix.riad.event.template"].search(
            [("event_kind", "=", "privatisation_weekend")], limit=1
        )
        start = fields.Datetime.to_datetime(self.date_start)
        end = fields.Datetime.to_datetime(self.check_out_date())
        event = self.env["intellix.riad.event"].create(
            {
                "name": "Privatisation — %s" % self.name,
                "establishment_id": self.establishment_id.id,
                "partner_id": self.partner_id.id,
                "date_start": start,
                "date_end": end,
                "guest_count": self.guest_count,
                "event_kind": "privatisation_weekend",
                "template_id": template.id if template else False,
                "state": "confirmed",
                "reservation_ids": [(6, 0, self.reservation_ids.ids)],
            }
        )
        self.event_id = event.id
        return event

    def action_confirm(self, acknowledge_conflicts=False):
        for rec in self:
            if rec.state in ("confirmed", "done"):
                continue
            conflicts = rec.collect_conflicts()
            rec.conflict_html = rec._conflicts_html(conflicts)
            if conflicts and not acknowledge_conflicts:
                raise UserError(
                    "Des réservations existent déjà sur cette période. "
                    "Relisez la liste des conflits et cochez la confirmation "
                    "avant de privatiser. Rien ne sera écrasé."
                )
            rec._create_room_holds()
            rec._close_channex()
            rec.state = "confirmed"
            rec._ensure_event()
            rec.message_post(
                body="Privatisation confirmée. Chambres libres bloquées, "
                "Channex fermé, restaurant et bien-être externe dédiés au groupe."
            )
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                continue
            rec._release_channex()
            holds = rec.reservation_ids.filtered(
                lambda r: (r.client_nom or "").startswith("Privatisation —")
            )
            if holds and hasattr(holds, "action_cancel"):
                holds.action_cancel()
            rec.state = "cancelled"
        return True

    def action_release(self):
        for rec in self:
            if rec.state != "confirmed":
                continue
            rec._release_channex()
            rec.state = "done"
            rec.message_post(
                body="Privatisation terminée : ressources rouvertes "
                "(lendemain de la dernière nuit)."
            )
        return True

    @api.model
    def cron_release_ended(self):
        today = fields.Date.context_today(self)
        ended = self.search(
            [("state", "=", "confirmed"), ("date_end", "<", today)]
        )
        ended.action_release()
        return True


class IntellixRiadPrivatisationWizard(models.TransientModel):
    _name = "intellix.riad.privatisation.wizard"
    _description = "Assistant privatisation complète"

    establishment_id = fields.Many2one(
        "intellix.riad.establishment", required=True
    )
    name = fields.Char(string="Groupe / intitulé", required=True)
    partner_id = fields.Many2one("res.partner", string="Client")
    date_start = fields.Date(string="Début", required=True)
    date_end = fields.Date(string="Fin (dernière nuit)", required=True)
    guest_count = fields.Integer(string="Personnes", default=6)
    notes = fields.Text()
    conflict_html = fields.Html(string="Conflits détectés", readonly=True)
    has_conflicts = fields.Boolean()
    acknowledge_conflicts = fields.Boolean(
        string="J'ai lu les conflits : les réservations existantes ne seront pas écrasées"
    )

    @api.onchange("establishment_id", "date_start", "date_end")
    def _onchange_preview_conflicts(self):
        Privatisation = self.env["intellix.riad.privatisation"]
        rows = Privatisation._collect_conflicts(
            self.establishment_id, self.date_start, self.date_end
        )
        self.has_conflicts = bool(rows)
        self.conflict_html = Privatisation._conflicts_html(rows)

    def action_preview(self):
        self.ensure_one()
        self._onchange_preview_conflicts()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_confirm(self):
        self.ensure_one()
        if not self.date_start or not self.date_end or self.date_end < self.date_start:
            raise UserError("Indiquez une plage de dates valide.")
        Privatisation = self.env["intellix.riad.privatisation"]
        rows = Privatisation._collect_conflicts(
            self.establishment_id, self.date_start, self.date_end
        )
        if rows and not self.acknowledge_conflicts:
            self.has_conflicts = True
            self.conflict_html = Privatisation._conflicts_html(rows)
            raise UserError(
                "Des réservations existent déjà. Cochez la case de confirmation "
                "pour continuer sans les écraser, ou changez les dates."
            )
        rec = Privatisation.create(
            {
                "name": self.name,
                "establishment_id": self.establishment_id.id,
                "partner_id": self.partner_id.id,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "guest_count": self.guest_count,
                "notes": self.notes,
            }
        )
        rec.action_confirm(acknowledge_conflicts=bool(rows and self.acknowledge_conflicts))
        return {
            "type": "ir.actions.act_window",
            "name": rec.name,
            "res_model": "intellix.riad.privatisation",
            "res_id": rec.id,
            "view_mode": "form",
            "target": "current",
        }
