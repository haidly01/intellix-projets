# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

SKIP_CALENDAR_SYNC_CTX = "doorway_skip_calendar_sync"
SKIP_ACTIVITY_SYNC_CTX = "doorway_skip_activity_sync"

# Fiches commerciales : opportunité CRM + partenariat Coins Québec.
DOORWAY_SYNC_MODELS = ("crm.lead", "coins.quebec.partenariat", "res.partner")


class DoorwayMailActivity(models.Model):
    _inherit = "mail.activity"

    crm_lead_id = fields.Many2one(
        "crm.lead",
        string="Opportunité",
        compute="_compute_crm_lead_id",
        store=True,
        index=True,
    )
    crm_team_id = fields.Many2one(
        "crm.team",
        related="crm_lead_id.team_id",
        store=True,
        string="Pipeline",
    )
    doorway_scheduled_start = fields.Datetime(
        string="Date et heure planifiées",
        help="Heure de début pour l'événement calendrier lié.",
    )
    doorway_scheduled_duration = fields.Integer(
        string="Durée (min)",
        default=30,
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        ctx = self.env.context
        active_model = ctx.get("active_model") or ctx.get("default_res_model")
        if active_model == "coins.quebec.partenariat" and "coins.quebec.partenariat" in self.env:
            model = self.env["ir.model"].sudo()._get("coins.quebec.partenariat")
            res_id = ctx.get("active_id") or ctx.get("default_res_id") or defaults.get("res_id")
            if model:
                defaults["res_model_id"] = model.id
                defaults["res_model"] = "coins.quebec.partenariat"
            if res_id:
                defaults["res_id"] = res_id
        return defaults

    @api.depends("res_model", "res_id")
    def _compute_crm_lead_id(self):
        for act in self:
            if act.res_model == "crm.lead" and act.res_id:
                act.crm_lead_id = act.res_id
            else:
                act.crm_lead_id = False

    def _doorway_related_record(self):
        self.ensure_one()
        if (
            self.res_model
            and self.res_id
            and self.res_model in self.env
        ):
            rec = self.env[self.res_model].sudo().browse(self.res_id)
            return rec if rec.exists() else False
        return False

    def _doorway_is_syncable(self):
        """Vrai RDV seulement (heure bookée). To-Do / Call / relance restent dans le chatter.

        Avant, toute activité crm.lead / CQ créait un événement à 9 h Toronto.
        Le calendrier de Martin chargeait ~1100 To-Do par semaine (~1,5 s).
        """
        self.ensure_one()
        if self.res_model not in DOORWAY_SYNC_MODELS:
            return False
        if not self.active:
            return False
        if self.res_model not in self.env:
            return False
        if self.doorway_scheduled_start:
            return True
        category = self.activity_type_id.category if self.activity_type_id else ""
        if category == "meeting" and self.calendar_event_id:
            return True
        return False

    def _doorway_calendar_event_name(self):
        self.ensure_one()
        record = self._doorway_related_record()
        record_name = (
            record.display_name
            if record
            else (self.crm_lead_id.name if self.crm_lead_id else self.res_name)
        )
        type_name = self.activity_type_id.name or _("Activité")
        summary = self.summary or ""
        label = "[%s] %s" % (type_name, record_name or "")
        if summary:
            label = "%s — %s" % (label, summary)
        return label

    def _doorway_calendar_start_stop(self):
        self.ensure_one()
        if self.doorway_scheduled_start:
            start = fields.Datetime.to_datetime(self.doorway_scheduled_start)
            minutes = self.doorway_scheduled_duration or 30
            return start, start + timedelta(minutes=minutes)
        user = self.user_id or self.env.user
        tz_name = user.tz or self.env.user.tz or "America/Toronto"
        tz = pytz.timezone(tz_name)
        day = fields.Date.to_date(self.date_deadline)
        start_local = tz.localize(datetime.combine(day, time(9, 0)))
        stop_local = start_local + timedelta(minutes=self.doorway_scheduled_duration or 30)
        return (
            start_local.astimezone(pytz.UTC).replace(tzinfo=None),
            stop_local.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    @api.model
    def _doorway_migrate_existing_activities_to_calendar(self, batch_size=200):
        """One-shot : activités commerciales actives sans événement calendrier."""
        models = [m for m in DOORWAY_SYNC_MODELS if m in self.env]
        Activity = self.sudo()
        # Uniquement les échéances à venir — pas les milliers d'historiques.
        activities = Activity.search(
            [
                ("res_model", "in", models),
                ("date_deadline", ">=", fields.Date.context_today(self)),
                ("active", "=", True),
                ("calendar_event_id", "=", False),
            ]
        )
        to_sync = activities.filtered(lambda a: a._doorway_is_syncable())
        for index in range(0, len(to_sync), batch_size):
            chunk = to_sync[index : index + batch_size]
            chunk._doorway_create_calendar_event()
            _logger.info(
                "doorway_crm: migration calendrier — lot de %s activité(s)",
                len(chunk),
            )
        if "calendar.event" in self.env:
            self.env["calendar.event"].sudo()._doorway_backfill_missing_activities()
        return len(to_sync)

    def _doorway_create_calendar_event(self):
        """Crée ou met à jour l'événement calendrier du commercial assigné."""
        Event = self.env["calendar.event"].sudo().with_context(
            **{SKIP_ACTIVITY_SYNC_CTX: True}
        )
        IrModel = self.env["ir.model"].sudo()
        for activity in self.filtered(lambda a: a._doorway_is_syncable()):
            start, stop = activity._doorway_calendar_start_stop()
            partner_ids = []
            if activity.user_id and activity.user_id.partner_id:
                partner_ids.append((4, activity.user_id.partner_id.id))
            record = activity._doorway_related_record()
            rec_name = record.display_name if record else ""
            rec_email = ""
            if record:
                if "email_from" in record._fields and record.email_from:
                    rec_email = record.email_from
                elif "partner_id" in record._fields and record.partner_id:
                    rec_email = record.partner_id.email or ""
            lead_line = "Lead : %s" % rec_name
            if rec_email:
                lead_line = "%s — %s" % (lead_line, rec_email)
            note = activity.note or ""
            description = ("%s\n%s" % (note, lead_line)).strip() if note else lead_line
            model = IrModel._get(activity.res_model)
            vals = {
                "name": activity._doorway_calendar_event_name(),
                "start": start,
                "stop": stop,
                "description": description,
                "user_id": activity.user_id.id or self.env.user.id,
                "partner_ids": partner_ids,
                "res_id": activity.res_id,
            }
            if model:
                vals["res_model_id"] = model.id
            if (
                activity.res_model == "crm.lead"
                and "opportunity_id" in Event._fields
            ):
                vals["opportunity_id"] = activity.res_id
            if activity.calendar_event_id:
                activity.calendar_event_id.with_context(
                    **{SKIP_ACTIVITY_SYNC_CTX: True}
                ).write(vals)
            else:
                event = Event.create(vals)
                activity.with_context(**{SKIP_CALENDAR_SYNC_CTX: True}).write(
                    {"calendar_event_id": event.id}
                )

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        if self.env.context.get(SKIP_CALENDAR_SYNC_CTX):
            return activities
        to_sync = activities.filtered(lambda a: a._doorway_is_syncable())
        if to_sync:
            to_sync._doorway_create_calendar_event()
        return activities

    def write(self, vals):
        if self.env.context.get(SKIP_CALENDAR_SYNC_CTX) or self.env.context.get(
            "mail_activity_meeting_update"
        ):
            return super().write(vals)
        res = super().write(vals)
        sync_fields = {
            "date_deadline",
            "doorway_scheduled_start",
            "doorway_scheduled_duration",
            "note",
            "summary",
            "user_id",
            "activity_type_id",
            "res_id",
            "res_model",
            "active",
        }
        if sync_fields.intersection(vals.keys()):
            self.filtered(lambda a: a._doorway_is_syncable())._doorway_create_calendar_event()
        return res

    def unlink(self):
        events = self.mapped("calendar_event_id")
        res = super().unlink()
        events.sudo().with_context(**{SKIP_ACTIVITY_SYNC_CTX: True}).unlink()
        return res

    def action_done(self):
        events = self.filtered("calendar_event_id").mapped("calendar_event_id")
        res = super().action_done()
        events.sudo().with_context(**{SKIP_ACTIVITY_SYNC_CTX: True}).unlink()
        return res
