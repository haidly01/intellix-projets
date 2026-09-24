# -*- coding: utf-8 -*-
"""Disponibilité calendrier — agents IA et humains."""
from datetime import datetime, timedelta

import pytz

from odoo import fields


class CalendarAvailabilityService:
    def __init__(self, env):
        self.env = env

    def _parse_dt(self, value, tz_name=None):
        if isinstance(value, datetime):
            dt = value
        else:
            dt = fields.Datetime.from_string(value)
        if tz_name:
            tz = pytz.timezone(tz_name)
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
            dt = dt.astimezone(tz)
        return dt

    def _partner_from_ref(self, ref):
        Partner = self.env["res.partner"].sudo()
        if isinstance(ref, int):
            return Partner.browse(ref).exists()
        if isinstance(ref, str) and ref.isdigit():
            return Partner.browse(int(ref)).exists()
        user = self.env["res.users"].sudo().search([("login", "=", ref)], limit=1)
        if user:
            return user.partner_id
        partner = Partner.search([("email", "=", ref)], limit=1)
        if partner:
            return partner
        profile = self.env["doorway.agent.profile"].sudo().browse(
            int(ref) if str(ref).isdigit() else 0
        )
        if profile and profile.calendar_partner_id:
            return profile.calendar_partner_id
        return Partner

    def check_availability(self, partner_refs, start, stop, tz_name=None):
        """Retourne disponibilité et conflits pour une ou plusieurs personnes."""
        start_dt = self._parse_dt(start, tz_name)
        stop_dt = self._parse_dt(stop, tz_name)
        partners = self.env["res.partner"]
        details = []
        for ref in partner_refs:
            partner = self._partner_from_ref(ref)
            if not partner:
                details.append({"ref": ref, "available": False, "error": "introuvable"})
                continue
            partners |= partner
            busy_map = partner._get_busy_calendar_events(
                start_dt.astimezone(pytz.UTC),
                stop_dt.astimezone(pytz.UTC),
            )
            conflicts = busy_map.get(partner.id, self.env["calendar.event"])
            details.append(
                {
                    "partner_id": partner.id,
                    "partner_name": partner.name,
                    "available": not conflicts,
                    "conflicts": [
                        {
                            "id": e.id,
                            "name": e.name,
                            "start": fields.Datetime.to_string(e.start),
                            "stop": fields.Datetime.to_string(e.stop),
                        }
                        for e in conflicts
                    ],
                }
            )
        all_available = all(d.get("available") for d in details if "error" not in d)
        return {
            "available": all_available and bool(details),
            "start": fields.Datetime.to_string(start_dt.astimezone(pytz.UTC).replace(tzinfo=None)),
            "stop": fields.Datetime.to_string(stop_dt.astimezone(pytz.UTC).replace(tzinfo=None)),
            "participants": details,
        }

    def find_free_slots(
        self,
        partner_refs,
        day,
        duration_minutes=30,
        tz_name="America/Toronto",
        work_start=9,
        work_end=17,
        slot_step=30,
    ):
        """Cherche des créneaux libres sur une journée (heures ouvrables)."""
        tz = pytz.timezone(tz_name)
        if isinstance(day, str):
            day_date = fields.Date.from_string(day)
        else:
            day_date = day
        start_local = tz.localize(datetime.combine(day_date, datetime.min.time().replace(hour=work_start)))
        end_local = tz.localize(datetime.combine(day_date, datetime.min.time().replace(hour=work_end)))
        duration = timedelta(minutes=duration_minutes)
        step = timedelta(minutes=slot_step)
        slots = []
        cursor = start_local
        while cursor + duration <= end_local:
            slot_stop = cursor + duration
            result = self.check_availability(
                partner_refs,
                cursor,
                slot_stop,
                tz_name=tz_name,
            )
            if result.get("available"):
                slots.append(
                    {
                        "start": fields.Datetime.to_string(
                            cursor.astimezone(pytz.UTC).replace(tzinfo=None)
                        ),
                        "stop": fields.Datetime.to_string(
                            slot_stop.astimezone(pytz.UTC).replace(tzinfo=None)
                        ),
                        "start_local": cursor.strftime("%H:%M"),
                        "stop_local": slot_stop.strftime("%H:%M"),
                    }
                )
            cursor += step
        return {"day": fields.Date.to_string(day_date), "slots": slots, "timezone": tz_name}
