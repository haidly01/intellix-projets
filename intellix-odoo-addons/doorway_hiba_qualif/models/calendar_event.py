# -*- coding: utf-8 -*-

from collections import OrderedDict
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models

MARTIN_LOGIN = "martin@agencedoorway.com"
MARTIN_TZ = "America/Toronto"
SLOT_MINUTES = 30
SLOT_HOURS = (9, 10, 11, 13, 14)


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    hiba_booked_by = fields.Many2one("res.users", string="Booké par", index=True)
    hiba_presence = fields.Selection(
        [
            ("booked", "Booké"),
            ("present", "Présent"),
            ("noshow", "Absent"),
        ],
        string="Présence (Hiba)",
        default="booked",
        index=True,
    )

    @api.model
    def doorway_martin_user(self):
        return self.env["res.users"].sudo().search(
            [("login", "=", MARTIN_LOGIN)], limit=1
        )

    @api.model
    def doorway_martin_busy_domain(self, user, slot_utc, minutes=SLOT_MINUTES):
        """Tout événement où Martin est organisateur ou invité bloque le créneau."""
        return [
            "|",
            ("user_id", "=", user.id),
            ("partner_ids", "in", [user.partner_id.id]),
            ("start", "<", slot_utc + timedelta(minutes=minutes)),
            ("stop", ">", slot_utc),
        ]

    @api.model
    def doorway_martin_free_slots(self, days=30, limit=400):
        """Créneaux Martin — lun–ven 9h–15h Toronto, pause 12h–13h, 30 min."""
        user = self.doorway_martin_user()
        if not user:
            return [], user
        tz = pytz.timezone(MARTIN_TZ)
        now = datetime.now(tz)
        slots = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        Event = self.sudo()
        for _ in range(days):
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for hour in SLOT_HOURS:
                for minute in (0, 30):
                    slot_local = day.replace(hour=hour, minute=minute)
                    if slot_local <= now:
                        continue
                    slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    if Event.search_count(
                        self.doorway_martin_busy_domain(user, slot_utc)
                    ):
                        continue
                    slots.append((slot_utc, slot_local))
                    if len(slots) >= limit:
                        return slots, user
        return slots, user

    @api.model
    def doorway_martin_slots_ui(self):
        """Même structure que la page publique /intellix/rdv/martin."""
        slots, user = self.doorway_martin_free_slots()
        if not user:
            return []
        months_fr = [
            "jan", "fév", "mar", "avr", "mai", "jun",
            "jul", "aoû", "sep", "oct", "nov", "déc",
        ]
        weekdays_fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        by_day = OrderedDict()
        for slot_utc, slot_local in slots:
            day_key = slot_local.strftime("%Y-%m-%d")
            if day_key not in by_day:
                wd = weekdays_fr[slot_local.weekday()]
                by_day[day_key] = {
                    "date": day_key,
                    "label": f"{wd} {slot_local.day} {months_fr[slot_local.month - 1]}",
                    "times": [],
                    "time_values": {},
                }
            display = slot_local.strftime("%H:%M")
            by_day[day_key]["times"].append(display)
            by_day[day_key]["time_values"][display] = slot_utc.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        result = []
        for day in by_day.values():
            day["count"] = len(day["times"])
            result.append(day)
        return result
