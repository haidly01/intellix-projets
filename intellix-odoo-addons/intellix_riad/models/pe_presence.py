# -*- coding: utf-8 -*-

from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


PUNCH_KINDS = ("present", "late", "leave", "illness", "unjustified")

KIND_TO_STATUS = {
    "present": "present",
    "late": "present",
    "leave": "conge",
    "illness": "absent",
    "unjustified": "absent",
}

KIND_TO_ABSENCE = {
    "leave": "planned",
    "illness": "illness",
    "unjustified": "unjustified",
}

KIND_LABELS = {
    "present": "Présent",
    "late": "Retard",
    "leave": "Absent (congé planifié)",
    "illness": "Absent (maladie)",
    "unjustified": "Absent (non justifiée)",
}

TRACKED_PUNCH_FIELDS = (
    "statut_jour",
    "absence_kind",
    "heure_debut",
    "minutes_late",
    "date",
    "riad_note",
)


def _profile_establishment(env, employee):
    if not employee:
        return env["intellix.riad.establishment"]
    profile = env["pe.employee.profile"].search(
        [
            ("employee_id", "=", employee.id),
            ("riad_establishment_id", "!=", False),
        ],
        limit=1,
    )
    return profile.riad_establishment_id


class PePresenceLogRiad(models.Model):
    _inherit = "pe.presence.log"

    source = fields.Selection(
        selection_add=[("riad_punch", "Pointage hébergement")],
        ondelete={"riad_punch": lambda recs: recs.write({"source": False})},
    )
    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        compute="_compute_riad_establishment_id",
        store=True,
        index=True,
    )

    @api.depends("employee_id")
    def _compute_riad_establishment_id(self):
        for rec in self:
            rec.riad_establishment_id = _profile_establishment(self.env, rec.employee_id)


class PePresenceSummaryRiad(models.Model):
    _inherit = "pe.presence.summary"

    minutes_late = fields.Integer(string="Minutes de retard", default=0)
    absence_kind = fields.Selection(
        [
            ("planned", "Congé planifié"),
            ("unplanned", "Non justifiée"),
            ("illness", "Maladie"),
            ("unjustified", "Non justifiée"),
        ],
        string="Motif d'absence",
    )
    riad_note = fields.Char(string="Note pointage")
    riad_punch = fields.Boolean(
        string="Saisi depuis le Module Hébergement",
        default=False,
        help="Protège ce résumé contre l'écrasement par le cron VICIdial de people_engine.",
    )
    riad_locked = fields.Boolean(
        string="Mois clos (rapport envoyé)",
        default=False,
        help="Verrouillé après l'envoi du rapport mensuel au comptable.",
    )
    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        compute="_compute_riad_establishment_id",
        store=True,
        index=True,
    )
    riad_correction_ids = fields.One2many(
        "intellix.riad.presence.correction",
        "summary_id",
        string="Historique des corrections",
    )

    @api.depends("employee_id")
    def _compute_riad_establishment_id(self):
        for rec in self:
            rec.riad_establishment_id = _profile_establishment(self.env, rec.employee_id)

    def riad_kind(self):
        self.ensure_one()
        if self.statut_jour == "conge" or self.absence_kind == "planned":
            return "leave"
        if self.statut_jour == "absent":
            if self.absence_kind == "illness":
                return "illness"
            return "unjustified"
        if self.statut_jour == "present" and (self.minutes_late or 0) > 0:
            return "late"
        if self.statut_jour == "present":
            return "present"
        return False

    def riad_status_label(self):
        self.ensure_one()
        kind = self.riad_kind()
        if kind == "late":
            arrival = self.riad_arrival_label()
            return "Retard (%s)" % arrival if arrival else "Retard"
        return KIND_LABELS.get(kind) or "—"

    def riad_status_css(self):
        self.ensure_one()
        kind = self.riad_kind()
        if kind == "late":
            return "late"
        if kind == "present":
            return "present"
        if kind in ("leave", "illness", "unjustified"):
            return "absent"
        return "muted"

    def riad_arrival_label(self):
        self.ensure_one()
        if not self.heure_debut:
            return ""
        local = fields.Datetime.context_timestamp(self, self.heure_debut)
        return "%sh%02d" % (local.hour, local.minute)

    def riad_snapshot_label(self):
        self.ensure_one()
        label = self.riad_status_label()
        return "%s — %s" % (self.date, label) if self.date else label

    def _assert_punch_manager(self):
        user = self.env.user
        if user.has_group("intellix_riad.group_riad_manager") or self.env.is_admin():
            return
        raise AccessError(
            "Seul le compte gérante (manager) peut pointer ou corriger les présences."
        )

    def _month_is_locked(self, establishment, day):
        if not establishment or not day:
            return False
        key = "%04d-%02d" % (day.year, day.month)
        return (establishment.payroll_last_sent_month or "") == key

    def _check_editable(self, day=None, establishment=None):
        self._assert_punch_manager()
        if not self:
            if self._month_is_locked(establishment, day):
                raise UserError(
                    "Ce mois est clos : le rapport a déjà été envoyé au comptable. "
                    "Plus aucune correction n'est possible."
                )
            return
        for rec in self:
            rec_day = day or rec.date
            estab = establishment or rec.riad_establishment_id
            if rec.riad_locked or self._month_is_locked(estab, rec_day):
                raise UserError(
                    "Ce mois est clos : le rapport a déjà été envoyé au comptable. "
                    "Plus aucune correction n'est possible."
                )

    def _parse_arrival(self, arrival, day):
        if not arrival:
            return False
        if isinstance(arrival, datetime):
            return fields.Datetime.to_datetime(arrival)
        text = str(arrival).strip().lower().replace("h", ":")
        if not text:
            return False
        parts = text.split(":")
        try:
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError) as exc:
            raise UserError("Heure d'arrivée invalide.") from exc
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            raise UserError("Heure d'arrivée invalide.")
        local_now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        local_dt = local_now.replace(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=hours,
            minute=minutes,
            second=0,
            microsecond=0,
        )
        utc_dt = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        return utc_dt

    def _minutes_late(self, arrival_dt, expected_start):
        if not arrival_dt:
            return 1
        local = fields.Datetime.context_timestamp(self, arrival_dt)
        hours = int(expected_start or 0)
        minutes = int(round(((expected_start or 0) % 1) * 60))
        if minutes >= 60:
            hours += 1
            minutes = 0
        expected_local = local.replace(
            hour=min(max(hours, 0), 23),
            minute=min(max(minutes, 0), 59),
            second=0,
            microsecond=0,
        )
        return max(int((local - expected_local).total_seconds() // 60), 1)

    def _vals_for_kind(self, employee, kind, day, arrival=None, note=None, expected_start=9.0):
        if kind not in PUNCH_KINDS:
            raise UserError("Statut de pointage inconnu.")
        arrival_dt = False
        minutes_late = 0
        if kind == "late":
            arrival_dt = self._parse_arrival(arrival, day)
            if not arrival_dt:
                raise UserError("Pour un retard, indiquez l'heure d'arrivée saisie par la gérante.")
            minutes_late = self._minutes_late(arrival_dt, expected_start)
        elif kind == "present":
            arrival_dt = self._parse_arrival(arrival, day) if arrival else False
        return {
            "employee_id": employee.id,
            "date": day,
            "statut_jour": KIND_TO_STATUS[kind],
            "heure_debut": arrival_dt,
            "minutes_late": minutes_late,
            "absence_kind": KIND_TO_ABSENCE.get(kind, False),
            "riad_note": note or False,
            "riad_punch": True,
        }

    def _log_correction(self, previous_label, previous_value, new_label, new_value):
        self.ensure_one()
        self.env["intellix.riad.presence.correction"].create(
            {
                "summary_id": self.id,
                "employee_id": self.employee_id.id,
                "date": self.date,
                "establishment_id": self.riad_establishment_id.id,
                "changed_by_id": self.env.user.id,
                "changed_at": fields.Datetime.now(),
                "previous_label": previous_label,
                "new_label": new_label,
                "previous_value": previous_value,
                "new_value": new_value,
            }
        )

    @api.model
    def riad_upsert_punch(
        self,
        employee,
        kind,
        arrival=None,
        note=None,
        expected_start=9.0,
        day=None,
    ):
        """Saisie manuelle uniquement : aucune heure système, aucune géoloc."""
        self._assert_punch_manager()
        day = day or fields.Date.context_today(self)
        if isinstance(day, str):
            day = fields.Date.to_date(day)
        establishment = _profile_establishment(self.env, employee)
        rec = self.search(
            [("employee_id", "=", employee.id), ("date", "=", day)],
            limit=1,
        )
        rec._check_editable(day=day, establishment=establishment)
        vals = self._vals_for_kind(
            employee,
            kind,
            day,
            arrival=arrival,
            note=note,
            expected_start=expected_start,
        )
        if rec:
            previous_label = rec.riad_snapshot_label()
            previous_value = rec.riad_status_label()
            rec.with_context(riad_skip_correction_log=True).write(vals)
            rec.invalidate_recordset()
            new_label = rec.riad_snapshot_label()
            if previous_label != new_label:
                rec._log_correction(
                    previous_label,
                    previous_value,
                    new_label,
                    rec.riad_status_label(),
                )
        else:
            rec = self.with_context(riad_skip_correction_log=True).create(vals)
        return rec.id

    def write(self, vals):
        track = any(field in vals for field in TRACKED_PUNCH_FIELDS)
        if track and not self.env.context.get("riad_skip_correction_log"):
            for rec in self.filtered("riad_punch"):
                rec._check_editable(
                    day=vals.get("date") or rec.date,
                    establishment=rec.riad_establishment_id,
                )
                previous_label = rec.riad_snapshot_label()
                previous_value = rec.riad_status_label()
                super(PePresenceSummaryRiad, rec).write(vals)
                rec.invalidate_recordset()
                new_label = rec.riad_snapshot_label()
                if previous_label != new_label:
                    rec._log_correction(
                        previous_label,
                        previous_value,
                        new_label,
                        rec.riad_status_label(),
                    )
            others = self - self.filtered("riad_punch") if self else self
            return super(PePresenceSummaryRiad, others).write(vals) if others else True
        return super().write(vals)

    def _upsert_summary(self, employee_id, date, vals):
        rec = self.search(
            [("employee_id", "=", employee_id), ("date", "=", date)],
            limit=1,
        )
        if rec and rec.riad_punch:
            return rec
        return super()._upsert_summary(employee_id, date, vals)
