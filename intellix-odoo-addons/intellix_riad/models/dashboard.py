# -*- coding: utf-8 -*-

import logging
from calendar import monthrange
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .event_template import CHECKLIST_KINDS

_logger = logging.getLogger(__name__)

WEEKDAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
MONTHS_FR = [
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
WEEKDAYS_LONG = [
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche",
]
OTA_SOURCES = {"booking", "airbnb", "expedia", "channex"}
OTA_CHANNELS = {"ota"}
SITE_CHANNELS = {"website", "riad_website"}
OCCUPIED_STATES = ("draft", "confirmed", "in_progress")
EMPLACEMENT_ORDER = ("etage", "rdc")
EMPLACEMENT_LABEL = {"etage": "Étage", "rdc": "RDC"}


def _channel_css(source, channel):
    if (source or "") in OTA_SOURCES or (channel or "") in OTA_CHANNELS:
        return "booked"
    if (channel or "") in SITE_CHANNELS or (source or "") == "direct":
        if (channel or "") == "backoffice":
            return "booked-manual"
        return "booked-alt"
    if (channel or "") == "backoffice":
        return "booked-manual"
    return "booked-alt"


def _money_label(amount, symbol="€"):
    value = int(round(float(amount or 0)))
    raw = str(abs(value))
    parts = []
    while raw:
        parts.insert(0, raw[-3:])
        raw = raw[:-3]
    text = " ".join(parts) or "0"
    if value < 0:
        text = "-" + text
    return "%s%s" % (text, symbol)


def _today_label(day):
    return "%s %s %s %s" % (
        WEEKDAYS_LONG[day.weekday()],
        day.day,
        MONTHS_FR[day.month],
        day.year,
    )


def _hour_to_input(value):
    hours = int(value or 0)
    minutes = int(round(((value or 0) - hours) * 60))
    return "%02d:%02d" % (hours, minutes)


def _input_to_hour(value):
    if value in (None, False, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("h", ":")
    parts = text.split(":")
    hours = int(parts[0] or 0)
    minutes = int(parts[1] or 0) if len(parts) > 1 else 0
    return hours + minutes / 60.0


class IntellixRiadDashboard(models.AbstractModel):
    _name = "intellix.riad.dashboard"
    _description = "Agrégateur tableau de bord Module Hébergement"

    def _allowed_establishments(self):
        Establishment = self.env["intellix.riad.establishment"]
        user = self.env.user
        if user.has_group("intellix_riad.group_riad_manager") or self.env.is_admin():
            return Establishment.search([])
        return user.riad_establishment_ids.filtered("active")

    def _resolve_establishment(self, establishment_id=None):
        allowed = self._allowed_establishments()
        if establishment_id:
            chosen = allowed.filtered(lambda e: e.id == int(establishment_id))
            if chosen:
                return chosen[:1]
        return allowed[:1]

    def _reservations_in_range(self, property_id, start, end):
        return self.env["coins.reservation"].search(
            [
                ("property_id", "=", property_id),
                ("state", "in", list(OCCUPIED_STATES)),
                ("check_in", "<", end),
                ("check_out", ">", start),
            ]
        )

    def _occupies(self, reservation, day):
        return reservation.check_in <= day < reservation.check_out

    def _guest_label(self, reservation):
        return (
            reservation.client_nom
            or reservation.traveler_id.name
            or reservation.name
            or ""
        )

    def _week_grid(self, estab, start, days=7):
        rooms = estab.property_id.room_ids.filtered("active").sorted(
            lambda r: (
                EMPLACEMENT_ORDER.index(r.emplacement)
                if r.emplacement in EMPLACEMENT_ORDER
                else 9,
                r.sequence,
                r.id,
            )
        )
        end = start + timedelta(days=days)
        reservations = self._reservations_in_range(estab.property_id.id, start, end)
        by_room = defaultdict(list)
        for resa in reservations:
            by_room[resa.room_id.id].append(resa)
        day_list = [start + timedelta(days=i) for i in range(days)]
        groups = []
        grouped = defaultdict(list)
        for room in rooms:
            grouped[room.emplacement or "other"].append(room)
        for key in list(EMPLACEMENT_ORDER) + ["other"]:
            if key not in grouped:
                continue
            rows = []
            for room in grouped[key]:
                cells = []
                for day in day_list:
                    hit = next(
                        (r for r in by_room.get(room.id, []) if self._occupies(r, day)),
                        None,
                    )
                    if hit:
                        css = _channel_css(hit.source, hit.booking_channel)
                        guest = self._guest_label(hit)
                        if hit.is_demo:
                            css = "booked-demo"
                            if not (guest or "").startswith("[DÉMO]"):
                                guest = "[DÉMO] %s" % guest
                        cells.append(
                            {
                                "date": fields.Date.to_string(day),
                                "css": css,
                                "reservation_id": hit.id,
                                "guest": guest,
                                "is_demo": bool(hit.is_demo),
                            }
                        )
                    else:
                        cells.append(
                            {
                                "date": fields.Date.to_string(day),
                                "css": "free",
                                "reservation_id": False,
                                "guest": "",
                            }
                        )
                rows.append(
                    {
                        "id": room.id,
                        "name": room.name,
                        "emplacement": room.emplacement or "",
                        "emplacement_label": (
                            "étage"
                            if room.emplacement == "etage"
                            else EMPLACEMENT_LABEL.get(room.emplacement, "")
                        ),
                        "cells": cells,
                    }
                )
            groups.append(
                {
                    "emplacement": key,
                    "label": EMPLACEMENT_LABEL.get(key, ""),
                    "rooms": rows,
                }
            )
        return {
            "days": [
                {"key": fields.Date.to_string(d), "label": WEEKDAYS_FR[d.weekday()]}
                for d in day_list
            ],
            "groups": groups,
        }

    def _created_in_range(self, property_id, start, end):
        return self.env["coins.reservation"].search(
            [
                ("property_id", "=", property_id),
                ("create_date", ">=", fields.Datetime.to_datetime("%s 00:00:00" % fields.Date.to_string(start))),
                ("create_date", "<=", fields.Datetime.to_datetime("%s 23:59:59" % fields.Date.to_string(end))),
                ("state", "!=", "cancelled"),
            ]
        )

    def _split_booking_channels(self, reservations):
        ota = site = other = 0
        for resa in reservations:
            source = (resa.source or "").strip().lower()
            channel = (resa.booking_channel or "").strip().lower()
            if source in OTA_SOURCES or channel in OTA_CHANNELS:
                ota += 1
            elif channel in SITE_CHANNELS or source == "direct":
                site += 1
            else:
                other += 1
        return ota, site, other

    def _nightly_rate(self, resa):
        if resa.room_id and resa.room_id.price_per_night:
            return resa.room_id.price_per_night
        if resa.nights:
            return (resa.amount_property or 0) / float(resa.nights)
        return resa.amount_property or 0

    def _night_revenue(self, reservations):
        return sum(self._nightly_rate(resa) for resa in reservations)

    def _occupancy_counts(self, rooms, tonight):
        room_count = len(rooms) or 1
        occupied = len({r.room_id.id for r in tonight if r.room_id})
        if not any(r.room_id for r in tonight) and tonight:
            occupied = min(len(tonight), room_count)
        return occupied, room_count

    def _period_revenue(self, reservations, start, end):
        total = 0.0
        for resa in reservations:
            if not resa.check_in or not resa.check_out:
                continue
            occ_start = max(resa.check_in, start)
            occ_end = min(resa.check_out, end)
            nights = max((occ_end - occ_start).days, 0)
            total += self._nightly_rate(resa) * nights
        return total

    def _kpis(self, estab, today):
        rooms = estab.property_id.room_ids.filtered("active")
        tonight = self._reservations_in_range(
            estab.property_id.id, today, today + timedelta(days=1)
        )
        occupied, room_count = self._occupancy_counts(rooms, tonight)
        created_today = self._created_in_range(estab.property_id.id, today, today)
        ota, site, other = self._split_booking_channels(created_today)
        night_revenue = self._night_revenue(tonight)
        slots = estab.wellness_slot_ids.filtered(
            lambda s: s.state != "cancelled"
            and s.date_start
            and s.date_start.date() == today
        )
        wellness_amount = sum(slots.mapped("amount"))
        residents = len(slots.filtered(lambda s: s.guest_kind == "resident"))
        externes = len(slots.filtered(lambda s: s.guest_kind == "externe"))
        return {
            "occupancy_pct": "%s%%" % int(round(100.0 * occupied / room_count)),
            "occupancy_sub": _("%s chambre(s) / %s ce soir") % (occupied, room_count),
            "bookings_today": len(created_today),
            "bookings_sub": (
                _("%s via Channex · %s site direct · %s autre(s)") % (ota, site, other)
                if other
                else _("%s via Channex · %s site direct") % (ota, site)
            ),
            "revenue": _money_label(night_revenue + wellness_amount),
            "revenue_sub": _("Chambres + bien-être + resto"),
            "wellness_count": len(slots),
            "wellness_sub": _("%s résidente(s) · %s externe(s)") % (residents, externes),
            **self._response_time_kpi(estab),
        }

    def _response_time_kpi(self, estab):
        seconds = self.env["intellix.riad.experience.thread"].average_response_seconds(
            estab
        )
        if seconds is None:
            return {
                "reply_time": "—",
                "reply_sub": _("Agent + Anna · 30 derniers jours"),
                "reply_css": "",
            }
        if seconds < 60:
            label = _("%s s") % seconds
        elif seconds < 3600:
            label = _("%s min") % max(int(round(seconds / 60.0)), 1)
        else:
            label = _("%s h") % (round(seconds / 3600.0, 1))
        if seconds < 300:
            css, hint = "ok", _("Airbnb : optimal (< 5 min)")
        elif seconds < 3600:
            css, hint = "warn", _("Airbnb : au-dessus de 5 min")
        else:
            css, hint = "bad", _("Airbnb : pénalité (> 1 h)")
        return {"reply_time": label, "reply_sub": hint, "reply_css": css}

    def _wellness_today(self, estab, today):
        slots = estab.wellness_slot_ids.filtered(
            lambda s: s.state != "cancelled"
            and s.date_start
            and s.date_start.date() == today
        ).sorted("date_start")
        rows = []
        for slot in slots:
            who = slot.guest_name or ""
            if slot.guest_kind == "externe" and who and "externe" not in who.lower():
                who = "%s — externe" % who
            rows.append(
                {
                    "id": slot.id,
                    "who": who or (slot.practitioner_id.name or "Soin"),
                    "time": slot.date_start.strftime("%Hh%M") if slot.date_start else "",
                    "type": slot.type_id.name or "",
                    "css": slot.type_id.css_class or "massage",
                }
            )
        return rows

    def _can_punch(self):
        return self.env.user.has_group("intellix_riad.group_riad_manager") or self.env.is_admin()

    def _attendance_row(self, profile, summary, today, estab):
        name = profile.display_name or profile.employee_id.name or ""
        role = profile.riad_role_label()
        if role == "—":
            role = ""
        who = "%s — %s" % (name, role) if role else name
        locked = bool(
            summary
            and summary.riad_locked
            or self.env["pe.presence.summary"]._month_is_locked(estab, today)
        )
        if not summary:
            what, status, css, kind = "Non pointé", "Non pointé", "muted", False
        else:
            kind = summary.riad_kind()
            status = summary.riad_status_label()
            css = summary.riad_status_css()
            arrival = summary.riad_arrival_label()
            if kind == "late":
                what = "Arrivée %s" % arrival if arrival else "Retard"
            elif kind == "present":
                what = "Présent"
            elif kind == "leave":
                what = "Congé planifié"
            elif kind == "illness":
                what = "Maladie"
            elif kind == "unjustified":
                what = "Non justifiée"
            else:
                what = status
        return {
            "id": profile.id,
            "summary_id": summary.id if summary else False,
            "who": who,
            "name": name,
            "role": role,
            "what": what,
            "status": status,
            "css": css,
            "kind": kind,
            "locked": locked,
            "punched": bool(summary),
        }

    def _attendance_today(self, estab, today):
        profiles = estab._riad_staff_profiles()
        summaries = self.env["pe.presence.summary"].search(
            [
                ("employee_id", "in", profiles.mapped("employee_id").ids),
                ("date", "=", today),
            ]
        )
        by_emp = {row.employee_id.id: row for row in summaries}
        return [
            self._attendance_row(profile, by_emp.get(profile.employee_id.id), today, estab)
            for profile in profiles
        ]

    def _inbox(self, estab):
        items = []
        waiting = self.env["intellix.riad.experience.thread"].search(
            [
                ("establishment_id", "=", estab.id),
                ("decision", "=", "escalate"),
                ("replied_at", "=", False),
            ],
            order="inbound_at desc",
            limit=5,
        )
        for thread in waiting:
            items.append(
                {
                    "kind": "experience",
                    "icon": "!",
                    "css": "ico-booking",
                    "title": _("Créateur d'Expérience — Anna doit répondre"),
                    "snippet": (thread.inbound_text or thread.name or "")[:80],
                    "res_id": thread.id,
                    "res_model": "intellix.riad.experience.thread",
                }
            )
        recent = self.env["coins.reservation"].search(
            [
                ("property_id", "=", estab.property_id.id),
                ("source", "in", list(OTA_SOURCES)),
                ("state", "!=", "cancelled"),
            ],
            order="create_date desc",
            limit=5,
        )
        for resa in recent:
            items.append(
                {
                    "kind": "booking",
                    "icon": "B",
                    "css": "ico-booking",
                    "title": "%s — nouvelle demande"
                    % (dict(resa._fields["source"].selection).get(resa.source) or "OTA"),
                    "snippet": "%s, %s nuit%s"
                    % (
                        resa.room_id.name or "Chambre",
                        resa.nights or 0,
                        "s" if (resa.nights or 0) > 1 else "",
                    ),
                    "res_id": resa.id,
                }
            )
        return items[:5]

    def _thread_items(self, estab, channels=None, limit=20):
        domain = [("establishment_id", "=", estab.id)]
        if channels:
            domain.append(("channel", "in", list(channels)))
        threads = self.env["intellix.riad.experience.thread"].search(
            domain, order="inbound_at desc, id desc", limit=limit
        )
        items = []
        for thread in threads:
            channel = thread.channel or "other"
            if channel in ("booking", "airbnb"):
                kind, css, icon = "booking", "ico-booking", "B"
            elif channel in ("messenger", "other"):
                kind, css, icon = "social", "ico-tiktok", "T"
            else:
                kind, css, icon = "mail", "ico-mail", "✉"
            items.append(
                {
                    "id": thread.id,
                    "kind": kind,
                    "icon": icon,
                    "css": css,
                    "title": thread.name or dict(thread._fields["channel"].selection).get(channel) or "Message",
                    "snippet": (thread.inbound_text or "")[:140],
                    "meta": thread.inbound_at.strftime("%d/%m %Hh%M") if thread.inbound_at else "",
                    "res_id": thread.id,
                    "res_model": "intellix.riad.experience.thread",
                }
            )
        return items

    @api.model
    def get_inbox_data(self, establishment_id=None):
        payload, estab, _today = self._base_screen(establishment_id)
        payload["items"] = []
        if not estab:
            return payload
        bookings = self._inbox(estab)
        mails = self._thread_items(estab, ("email", "website", "whatsapp", "booking", "airbnb"))
        seen = set()
        items = []
        for row in bookings + mails:
            key = (row.get("kind"), row.get("res_id"), row.get("snippet"))
            if key in seen:
                continue
            seen.add(key)
            items.append(row)
        payload["items"] = items[:30]
        return payload

    SOCIAL_PLATFORMS = (
        ("instagram", "Instagram"),
        ("facebook", "Facebook"),
        ("tiktok", "TikTok"),
    )

    def _riad_social_accounts(self, estab):
        estab = estab.sudo()
        accounts = estab.social_account_ids
        if estab.social_account_id:
            accounts |= estab.social_account_id
        return accounts.filtered("active")

    def _ensure_social_pipeline(self, estab):
        estab = estab.sudo()
        if estab.social_pipeline_id:
            return estab.social_pipeline_id
        name = "Hébergement — %s" % (estab.name or estab.property_id.name or "Riad")
        Team = self.env["crm.team"].sudo()
        team = Team.search([("name", "=", name)], limit=1)
        if not team:
            team = Team.create({"name": name})
        estab.social_pipeline_id = team.id
        return team

    def _ensure_social_account(self, estab, platform):
        accounts = self._riad_social_accounts(estab).filtered(
            lambda a: a.platform == platform
        )
        if accounts:
            return accounts[0]
        Account = self.env["doorway.social.account"].sudo()
        name = "%s — %s" % (
            estab.name or estab.property_id.name or "Riad",
            dict(self.SOCIAL_PLATFORMS).get(platform, platform),
        )
        account = Account.create(
            {
                "name": name,
                "platform": platform,
                "connection_state": "disconnected",
                "pipeline_id": self._ensure_social_pipeline(estab).id,
            }
        )
        estab.sudo().write({"social_account_ids": [(4, account.id)]})
        if not estab.sudo().social_account_id:
            estab.sudo().social_account_id = account.id
        return account

    @api.model
    def get_social_data(self, establishment_id=None):
        payload, estab, _today = self._base_screen(establishment_id)
        payload.update({"items": [], "accounts": [], "posts": []})
        if not estab:
            return payload
        payload["items"] = self._thread_items(estab, ("messenger", "other"))
        linked = self._riad_social_accounts(estab)
        accounts = []
        for code, label in self.SOCIAL_PLATFORMS:
            acc = linked.filtered(lambda a: a.platform == code)[:1]
            state = acc.connection_state if acc else "disconnected"
            accounts.append(
                {
                    "platform": code,
                    "label": label,
                    "id": acc.id if acc else False,
                    "name": acc.name if acc else label,
                    "state": state or "disconnected",
                    "connected": state == "connected",
                    "state_label": (
                        "Connecté"
                        if state == "connected"
                        else "Expiré"
                        if state == "expired"
                        else "Non connecté"
                    ),
                }
            )
        payload["accounts"] = accounts
        posts = []
        if linked and "doorway.social.post" in self.env:
            Post = self.env["doorway.social.post"].sudo()
            rows = Post.search([("account_ids", "in", linked.ids)], limit=20)
            state_sel = dict(Post._fields["state"].selection)
            plat_sel = dict(Post._fields["platform"].selection)
            for post in rows:
                posts.append(
                    {
                        "id": post.id,
                        "title": post.name or (post.caption or "")[:80] or "Publication",
                        "caption": post.caption or "",
                        "platform": post.platform,
                        "platform_label": plat_sel.get(post.platform, post.platform),
                        "state": post.state,
                        "state_label": state_sel.get(post.state, post.state or ""),
                    }
                )
        payload["posts"] = posts
        return payload

    @api.model
    def connect_social_account(self, establishment_id, platform):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        if platform not in dict(self.SOCIAL_PLATFORMS):
            raise UserError(_("Réseau non pris en charge."))
        account = self._ensure_social_account(estab, platform)
        return {
            "account_id": account.id,
            "url": "/doorway/social/oauth/%s?account_id=%s" % (platform, account.id),
            "state": account.connection_state,
        }

    @api.model
    def publish_social_post(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        platform = values.get("platform") or "instagram"
        if platform not in dict(self.SOCIAL_PLATFORMS):
            raise UserError(_("Choisissez Instagram, Facebook ou TikTok."))
        caption = (values.get("caption") or "").strip()
        if not caption:
            raise UserError(_("Écrivez le texte de la publication."))
        account = self._riad_social_accounts(estab).filtered(
            lambda a: a.platform == platform
        )[:1]
        if not account:
            account = self._ensure_social_account(estab, platform)
        pipeline = self._ensure_social_pipeline(estab)
        Post = self.env["doorway.social.post"].sudo()
        # publish_now=False : sinon doorway peut cibler un compte Coins déjà connecté.
        result = Post.create_from_composer(
            {
                "pipeline_id": pipeline.id,
                "platform": platform,
                "post_format": values.get("post_format") or "publication",
                "caption": caption,
                "hashtags": values.get("hashtags") or "",
                "account_ids": account.ids,
                "publish_now": False,
            }
        )
        post = Post.browse((result or {}).get("id"))
        warning = (result or {}).get("warning") or ""
        if account.connection_state == "connected" and post:
            try:
                published = post.action_publish_now()
            except UserError as err:
                warning = err.args[0] if err.args else str(err)
            else:
                if isinstance(published, dict) and published.get("type"):
                    warning = _(
                        "Solde de crédits insuffisant : le post reste en brouillon."
                    )
        elif not warning:
            warning = _(
                "Compte %s non connecté : le texte est enregistré. "
                "Connectez le réseau pour le mettre en ligne."
            ) % dict(self.SOCIAL_PLATFORMS).get(platform, platform)
        return {
            "id": post.id if post else False,
            "state": post.state if post else False,
            "warning": warning,
        }

    def _events(self, estab, today):
        events = estab.event_ids.filtered(
            lambda e: e.state != "cancelled"
            and e.date_start
            and e.date_start.date() >= today
        ).sorted("date_start")[:6]
        rows = []
        for event in events:
            day = event.date_start.date()
            bits = []
            rooms = len(event.reservation_ids)
            if rooms:
                bits.append("%s chambre%s" % (rooms, "s" if rooms > 1 else ""))
            if event.meal_plan:
                bits.append(
                    dict(event._fields["meal_plan"].selection).get(event.meal_plan) or ""
                )
            if event.task_total_count:
                bits.append("%s tâches" % event.task_progress_label)
            rows.append(
                {
                    "id": event.id,
                    "date_chip": "%s %s" % (day.day, MONTHS_FR[day.month][:4] + "."),
                    "title": event.name,
                    "meta": " · ".join([b for b in bits if b]) or event.notes or "",
                }
            )
        return rows

    @api.model
    def get_dashboard_data(self, establishment_id=None):
        estab = self._resolve_establishment(establishment_id)
        today = fields.Date.context_today(self)
        user = self.env.user
        first = (user.name or "").split()[0]
        payload = {
            "user": {
                "name": first or user.name or "",
                "initial": (first[:1] or "R").upper(),
            },
            "today_label": _today_label(today),
            "establishments": [
                {"id": e.id, "name": e.name or e.property_id.name}
                for e in self._allowed_establishments()
            ],
            "establishment": False,
            "kpis": {},
            "week": {"days": [], "groups": []},
            "terrace": {},
            "wellness_today": [],
            "attendance_today": [],
            "inbox": [],
            "events": [],
            "pricing": {},
            "can_punch": self._can_punch(),
        }
        if not estab:
            return payload
        payload["establishment"] = {
            "id": estab.id,
            "name": estab.name or estab.property_id.name,
            "property_id": estab.property_id.id,
            "tiktok_handle": estab.tiktok_handle or "",
        }
        payload["kpis"] = self._kpis(estab, today)
        payload["week"] = self._week_grid(estab, today, days=7)
        payload["has_channex_demo"] = bool(
            self.env["coins.reservation"].search_count(
                [
                    ("property_id", "=", estab.property_id.id),
                    ("is_demo", "=", True),
                    ("state", "in", list(OCCUPIED_STATES)),
                ]
            )
        )
        payload["terrace"] = estab.terrace_payload(today)
        payload["wellness_today"] = self._wellness_today(estab, today)
        payload["attendance_today"] = self._attendance_today(estab, today)
        payload["inbox"] = self._inbox(estab)
        payload["events"] = self._events(estab, today)
        payload["pricing"] = estab.pricing_dashboard_payload()
        return payload

    FLEET_STALE_HOURS = 24
    FLEET_LODGING_TYPES = ("riad", "maison_hotes", "villa", "apartment")
    FLEET_TYPE_LABELS = {
        "riad": "Riad",
        "maison_hotes": "Maison d'hôtes",
        "villa": "Villa",
        "apartment": "Appartement",
        "other": "Hôtel",
        "pool_hammam": "Piscine / Hammam",
    }

    def _fleet_stale_hours(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "intellix_riad.channex_stale_hours", str(self.FLEET_STALE_HOURS)
        )
        try:
            return max(int(raw), 1)
        except (TypeError, ValueError):
            return self.FLEET_STALE_HOURS

    def _fleet_properties(self):
        Mapping = self.env["coins.channex.mapping"]
        mapped = Mapping.search([("kind", "=", "property")]).mapped("property_id")
        establishments = self._allowed_establishments()
        estab_props = establishments.mapped("property_id")
        user = self.env.user
        if (
            user.has_group("intellix_riad.group_riad_manager")
            or user.has_group("coins_marocain.group_coins_manager")
            or self.env.is_admin()
        ):
            lodging = self.env["coins.property"].search(
                [
                    ("active", "=", True),
                    ("property_type", "in", list(self.FLEET_LODGING_TYPES)),
                ]
            )
            return (lodging | mapped | estab_props).filtered("active")
        return estab_props.filtered("active")

    def _channex_live_index(self):
        """GET /properties — lecture seule. Vide si l'API ne répond pas."""
        try:
            from odoo.addons.coins_marocain.services.channex_service import (
                ChannexService,
            )

            svc = ChannexService(self.env)
            if not svc.ready:
                return {}
            data = svc.ping()
        except Exception:  # noqa: BLE001
            _logger.exception("fleet channex ping")
            return {}
        rows = data if isinstance(data, list) else [data] if data else []
        index = {}
        for row in rows:
            uid = (row or {}).get("id")
            attrs = (row or {}).get("attributes") or {}
            if uid:
                index[str(uid)] = {
                    "title": attrs.get("title") or attrs.get("name") or "",
                    "is_active": attrs.get("is_active") is not False,
                }
        return index

    def _dt_label(self, dt):
        if not dt:
            return "—"
        local = fields.Datetime.context_timestamp(self, dt)
        return local.strftime("%d/%m/%Y %Hh%M")

    def _channex_row_status(self, mapping, last_success, last_error, live, stale_hours):
        if last_error and (not last_success or last_error > last_success):
            return "error", _("Erreur de sync"), last_error or last_success, True
        if not mapping:
            return "disconnected", _("Déconnecté"), last_success, False
        uid = (mapping.channex_id or "").strip()
        if live:
            if uid not in live:
                return (
                    "disconnected",
                    _("Déconnecté (absent de Channex)"),
                    last_success,
                    True,
                )
            if not live[uid].get("is_active"):
                return (
                    "disconnected",
                    _("Déconnecté (Channex inactif)"),
                    last_success,
                    True,
                )
        if last_success:
            age_h = (fields.Datetime.now() - last_success).total_seconds() / 3600.0
            if age_h > stale_hours:
                return (
                    "disconnected",
                    _("Sync expirée (%s h)") % int(age_h),
                    last_success,
                    True,
                )
            return "active", _("Actif"), last_success, False
        if live and uid in live and live[uid].get("is_active"):
            return "active", _("Actif (Channex)"), False, False
        return "disconnected", _("Déconnecté"), False, True

    @api.model
    def get_fleet_data(self, period="today"):
        """Vue globale lecture seule — mêmes formules que le dashboard individuel."""
        today = fields.Date.context_today(self)
        if period == "30d":
            start = today - timedelta(days=29)
        elif period == "7d":
            start = today - timedelta(days=6)
        else:
            period = "today"
            start = today
        end = today + timedelta(days=1)
        stale_hours = self._fleet_stale_hours()
        properties = self._fleet_properties()
        establishments = self.env["intellix.riad.establishment"].sudo().search(
            [("property_id", "in", properties.ids), ("active", "=", True)]
        )
        estab_by_prop = {e.property_id.id: e for e in establishments if e.property_id}
        user = self.env.user
        first = (user.name or "").split()[0]
        payload = {
            "user": {
                "name": first or user.name or "",
                "initial": (first[:1] or "R").upper(),
            },
            "today_label": _today_label(today),
            "period": period,
            "stale_hours": stale_hours,
            "channex_live_count": 0,
            "channex_live_ok": False,
            "rows": [],
            "cities": [],
            "types": [],
            "alert_count": 0,
        }
        if not properties:
            return payload

        Mapping = self.env["coins.channex.mapping"]
        mappings = Mapping.search(
            [("kind", "=", "property"), ("property_id", "in", properties.ids)]
        )
        mapping_by_prop = {m.property_id.id: m for m in mappings}

        Push = self.env["coins.channex.push"]
        Calendar = self.env["coins.channex.calendar"]
        last_success = {}
        last_error = {}
        for rec in Push.search(
            [("property_id", "in", properties.ids)], order="write_date desc"
        ):
            pid = rec.property_id.id
            when = rec.write_date
            if rec.state == "done" and pid not in last_success:
                last_success[pid] = when
            if rec.state == "error" and pid not in last_error:
                last_error[pid] = when
        for rec in Calendar.search(
            [("property_id", "in", properties.ids)], order="write_date desc"
        ):
            pid = rec.property_id.id
            when = rec.write_date
            if rec.state == "done":
                prev = last_success.get(pid)
                if not prev or when > prev:
                    last_success[pid] = when
            if rec.state == "error":
                prev = last_error.get(pid)
                if not prev or when > prev:
                    last_error[pid] = when

        live = self._channex_live_index()
        payload["channex_live_count"] = len(live)
        payload["channex_live_ok"] = bool(live)

        stay = self.env["coins.reservation"].search(
            [
                ("property_id", "in", properties.ids),
                ("state", "in", list(OCCUPIED_STATES)),
                ("check_in", "<", end),
                ("check_out", ">", start),
            ]
        )
        created = self.env["coins.reservation"].search(
            [
                ("property_id", "in", properties.ids),
                ("create_date", ">=", fields.Datetime.to_datetime("%s 00:00:00" % fields.Date.to_string(start))),
                ("create_date", "<=", fields.Datetime.to_datetime("%s 23:59:59" % fields.Date.to_string(today))),
                ("state", "!=", "cancelled"),
            ]
        )
        stay_by_prop = defaultdict(list)
        created_by_prop = defaultdict(list)
        for resa in stay:
            stay_by_prop[resa.property_id.id].append(resa)
        for resa in created:
            created_by_prop[resa.property_id.id].append(resa)

        tonight_end = today + timedelta(days=1)
        rows = []
        cities = set()
        types = set()
        alert_count = 0
        for prop in properties:
            rooms = prop.room_ids.filtered("active")
            tonight = [
                r
                for r in stay_by_prop.get(prop.id, [])
                if r.check_in and r.check_out and r.check_in <= today < r.check_out
            ]
            occupied, room_count = self._occupancy_counts(rooms, tonight)
            occ_pct = int(round(100.0 * occupied / room_count))
            period_resas = stay_by_prop.get(prop.id, [])
            created_rows = created_by_prop.get(prop.id, [])
            ota, site, other = self._split_booking_channels(created_rows)
            estab = estab_by_prop.get(prop.id)
            wellness_amount = 0.0
            if estab and period == "today":
                slots = estab.wellness_slot_ids.filtered(
                    lambda s: s.state != "cancelled"
                    and s.date_start
                    and s.date_start.date() == today
                )
                wellness_amount = sum(slots.mapped("amount"))
            revenue = self._period_revenue(period_resas, start, end) + wellness_amount
            symbol = "€"
            if prop.currency_id and prop.currency_id.symbol:
                symbol = prop.currency_id.symbol
            mapping = mapping_by_prop.get(prop.id)
            status, status_label, sync_dt, critical = self._channex_row_status(
                mapping,
                last_success.get(prop.id),
                last_error.get(prop.id),
                live,
                stale_hours,
            )
            if critical:
                alert_count += 1
            ptype = prop.property_type or "other"
            if ptype == "other" and mapping:
                type_label = _("Hôtel")
            else:
                type_label = dict(self.FLEET_TYPE_LABELS).get(ptype, ptype)
            city = (prop.city or "").strip() or "—"
            cities.add(city)
            types.add(type_label)
            rows.append(
                {
                    "property_id": prop.id,
                    "establishment_id": estab.id if estab else False,
                    "name": prop.name or "",
                    "city": city,
                    "type": ptype,
                    "type_label": type_label,
                    "status": status,
                    "status_label": status_label,
                    "critical": critical,
                    "occupancy_pct": occ_pct,
                    "occupancy_label": "%s%%" % occ_pct,
                    "occupancy_sub": _("%s / %s") % (occupied, room_count),
                    "revenue": revenue,
                    "revenue_label": _money_label(revenue, symbol),
                    "bookings_channex": ota,
                    "bookings_direct": site,
                    "bookings_other": other,
                    "bookings_label": "%s / %s" % (ota, site),
                    "last_sync": fields.Datetime.to_string(sync_dt) if sync_dt else "",
                    "last_sync_label": self._dt_label(sync_dt),
                    "mapped": bool(mapping),
                    "channex_id": mapping.channex_id if mapping else "",
                }
            )
        rows.sort(
            key=lambda r: (not r["critical"], r["status"] != "error", (r["name"] or "").lower())
        )
        payload["rows"] = rows
        payload["cities"] = sorted(cities)
        payload["types"] = sorted(types)
        payload["alert_count"] = alert_count
        return payload

    def _calendar_cell(self, day, css="free", guest="", reservation_id=False, record_id=False):
        return {
            "date": fields.Date.to_string(day),
            "css": css,
            "guest": guest or "",
            "reservation_id": reservation_id,
            "record_id": record_id,
        }

    def _calendar_section(self, key, label, rows):
        return {
            "key": key,
            "section": key,
            "emplacement": key,
            "label": label,
            "rooms": rows,
        }

    def _calendar_extra_groups(self, estab, start, days):
        day_list = [start + timedelta(days=i) for i in range(days)]
        end = start + timedelta(days=days - 1)
        groups = []

        table_rows = []
        for table in self._active_tables(estab):
            cells = []
            for day in day_list:
                if table.booking_date == day and table.booking_guest:
                    cells.append(
                        self._calendar_cell(
                            day,
                            "booked-alt",
                            "%s · %s" % (table.booking_guest, table.booking_covers or table.seats),
                            record_id=table.id,
                        )
                    )
                else:
                    cells.append(self._calendar_cell(day))
            table_rows.append(
                {
                    "id": table.id,
                    "name": table.name,
                    "resource_type": "restaurant",
                    "emplacement_label": table.zone or "",
                    "cells": cells,
                }
            )
        groups.append(self._calendar_section("restaurant", "Restaurant", table_rows))

        slots = estab.wellness_slot_ids.filtered(
            lambda s: s.state != "cancelled"
            and s.date_start
            and start <= s.date_start.date() <= end
        )
        by_prac = defaultdict(list)
        for slot in slots:
            by_prac[slot.practitioner_id.id].append(slot)
        wellness_rows = []
        for practitioner in estab.practitioner_ids.filtered("active"):
            cells = []
            for day in day_list:
                hit = next(
                    (s for s in by_prac.get(practitioner.id, []) if s.date_start.date() == day),
                    None,
                )
                if hit:
                    when = hit.date_start.strftime("%Hh%M") if hit.date_start else ""
                    cells.append(
                        self._calendar_cell(
                            day,
                            "booked",
                            " · ".join(
                                part
                                for part in (hit.guest_name or hit.type_id.name or "Soin", when)
                                if part
                            ),
                            record_id=hit.id,
                        )
                    )
                else:
                    cells.append(self._calendar_cell(day))
            kind = practitioner.kind or (
                "staff" if practitioner.pe_profile_id else "external"
            )
            wellness_rows.append(
                {
                    "id": practitioner.id,
                    "name": practitioner.name,
                    "resource_type": "wellness",
                    "emplacement_label": (
                        "staff interne" if kind == "staff" else "prestataire"
                    ),
                    "cells": cells,
                }
            )
        groups.append(self._calendar_section("wellness", "Bien-être", wellness_rows))

        events = self.env["intellix.riad.event"].search(
            [
                ("establishment_id", "=", estab.id),
                ("state", "!=", "cancelled"),
                ("event_kind", "=", "excursion"),
            ]
        )
        excursion_rows = []
        for event in events:
            ev_start = event.day_start or (event.date_start.date() if event.date_start else None)
            ev_end = event.day_end or ev_start
            if not ev_start:
                continue
            cells = []
            for day in day_list:
                if ev_start <= day <= (ev_end or ev_start):
                    cells.append(
                        self._calendar_cell(day, "booked-manual", event.name, record_id=event.id)
                    )
                else:
                    cells.append(self._calendar_cell(day))
            excursion_rows.append(
                {
                    "id": event.id,
                    "name": event.name,
                    "resource_type": "excursion",
                    "emplacement_label": "",
                    "cells": cells,
                }
            )
        groups.append(self._calendar_section("excursion", "Excursions", excursion_rows))

        privs = self.env["intellix.riad.privatisation"].search(
            [
                ("establishment_id", "=", estab.id),
                ("state", "in", ("draft", "confirmed")),
                ("date_start", "<=", end),
                ("date_end", ">=", start),
            ]
        )
        priv_cells = []
        for day in day_list:
            hit = next(
                (p for p in privs if p.date_start and p.date_end and p.date_start <= day <= p.date_end),
                None,
            )
            if hit:
                priv_cells.append(
                    self._calendar_cell(
                        day,
                        "booked-alt",
                        hit.name,
                        record_id=hit.id,
                    )
                )
            else:
                priv_cells.append(self._calendar_cell(day))
        groups.append(
            self._calendar_section(
                "privatisation",
                _("Privatisation de la maison d'hôtes")
                if (estab.property_id.property_type or "") == "maison_hotes"
                else _("Privatisation du riad"),
                [
                    {
                        "id": "riad-entier",
                        "name": (
                            _("Maison d'hôtes entière")
                            if (estab.property_id.property_type or "") == "maison_hotes"
                            else _("Riad entier")
                        ),
                        "resource_type": "privatisation",
                        "emplacement_label": "",
                        "cells": priv_cells,
                    }
                ],
            )
        )
        return groups

    @api.model
    def get_calendar_data(self, establishment_id=None, days=14, date_from=None, date_to=None):
        estab = self._resolve_establishment(establishment_id)
        today = fields.Date.context_today(self)
        user = self.env.user
        first = (user.name or "").split()[0]
        payload = {
            "user": {
                "name": first or user.name or "",
                "initial": (first[:1] or "R").upper(),
            },
            "today_label": _today_label(today),
            "establishments": [
                {"id": e.id, "name": e.name or e.property_id.name}
                for e in self._allowed_establishments()
            ],
            "establishment": False,
            "grid": {"days": [], "groups": []},
            "reservation_groups": [],
            "period": {},
            "lodging_label": "établissement",
        }
        if not estab:
            return payload
        payload["establishment"] = {
            "id": estab.id,
            "name": estab.name or estab.property_id.name,
            "property_id": estab.property_id.id,
            "property_type": estab.property_id.property_type or "",
        }
        payload["lodging_label"] = (
            "maison d'hôtes"
            if (estab.property_id.property_type or "") == "maison_hotes"
            else "riad"
        )
        payload["has_channex_demo"] = bool(
            self.env["coins.reservation"].search_count(
                [
                    ("property_id", "=", estab.property_id.id),
                    ("is_demo", "=", True),
                    ("state", "in", list(OCCUPIED_STATES)),
                ]
            )
        )

        start = today
        if date_from:
            start = fields.Date.to_date(date_from) or today
        if date_to:
            end = fields.Date.to_date(date_to) or start
            span = max((end - start).days + 1, 1)
            span = min(span, 62)
        else:
            span = int(days or 14)
            end = start + timedelta(days=span - 1)

        payload["period"] = {
            "date_from": fields.Date.to_string(start),
            "date_to": fields.Date.to_string(end),
            "days": span,
            "month": "%04d-%02d" % (start.year, start.month),
        }

        grid = self._week_grid(estab, start, days=span)
        for group in grid["groups"]:
            floor = group.get("label") or ""
            group["key"] = "rooms-%s" % (group.get("emplacement") or "x")
            group["section"] = "rooms"
            group["label"] = "Chambres — %s" % floor if floor else "Chambres"
            for row in group.get("rooms") or []:
                row["resource_type"] = "room"
        grid["groups"] = list(grid["groups"]) + self._calendar_extra_groups(
            estab, start, span
        )
        payload["grid"] = grid
        payload["reservation_groups"] = estab.sudo().portal_reservation_groups(
            date_from=start, date_to=end
        )
        payload["payment_tabs"] = estab.sudo().portal_payment_tabs(
            date_from=start, date_to=end
        )
        payload["rooms"] = [
            {"id": room.id, "name": room.name}
            for room in estab.property_id.room_ids.filtered("active")
        ]
        payload["tables"] = [
            {"id": table.id, "name": table.name, "seats": table.seats}
            for table in self._active_tables(estab)
        ]
        payload["practitioners"] = [
            self._practitioner_row(row)
            for row in estab.practitioner_ids.filtered("active")
        ]
        payload["service_types"] = [
            {"id": row.id, "name": row.name}
            for row in self.env["intellix.riad.wellness.type"].search([])
        ]
        return payload

    def _base_screen(self, establishment_id=None):
        estab = self._resolve_establishment(establishment_id)
        today = fields.Date.context_today(self)
        user = self.env.user
        first = (user.name or "").split()[0]
        payload = {
            "user": {
                "name": first or user.name or "",
                "initial": (first[:1] or "R").upper(),
            },
            "today_label": _today_label(today),
            "establishments": [
                {"id": e.id, "name": e.name or e.property_id.name}
                for e in self._allowed_establishments()
            ],
            "establishment": False,
            "can_punch": self._can_punch(),
        }
        if estab:
            payload["establishment"] = {
                "id": estab.id,
                "name": estab.name or estab.property_id.name,
                "property_id": estab.property_id.id,
            }
        return payload, estab, today

    def _guest_count(self, reservation):
        for fname in ("voyageurs", "adults", "guest_count", "nb_guests", "pax"):
            if fname in reservation._fields:
                value = reservation[fname]
                if value:
                    return int(value)
        return 2

    def _active_tables(self, estab):
        return estab.table_ids.filtered("active")

    def _practitioner_row(self, row):
        kind = row.kind or ("staff" if row.pe_profile_id else "external")
        label = "Staff interne" if kind == "staff" else "Prestataire"
        return {
            "id": row.id,
            "name": row.name,
            "label": "%s — %s" % (row.name, label),
            "kind": kind,
            "kind_label": label,
            "type_ids": row.type_ids.ids,
            "types": ", ".join(row.type_ids.mapped("name")) or "Tous les soins",
        }

    def _staff_candidates(self, estab):
        used = set(estab.practitioner_ids.mapped("pe_profile_id").ids)
        rows = []
        for profile in estab._riad_staff_profiles():
            if profile.id in used:
                continue
            rows.append(
                {
                    "id": profile.id,
                    "name": profile.display_name
                    or (profile.employee_id.name if profile.employee_id else "")
                    or "",
                }
            )
        return rows

    def _current_hour(self):
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return now.hour + now.minute / 60.0

    @api.model
    def get_restaurant_data(self, establishment_id=None):
        payload, estab, today = self._base_screen(establishment_id)
        payload.update(
            {
                "tables": [],
                "half_board": [],
                "terrace": {},
                "mode_label": "Terrasse",
                "restaurant_hours": "",
                "revenue": "0€",
                "revenue_sub": "",
                "privatised": False,
                "residents": [],
                "tickets": [],
                "zones": [
                    {"id": "terrasse", "name": "Terrasse"},
                    {"id": "patio", "name": "Patio"},
                    {"id": "salon", "name": "Salon"},
                ],
                "menu": [],
                "menu_now": [],
                "company": "",
            }
        )
        if not estab:
            return payload
        privatised = self.env["intellix.riad.privatisation"].is_active_on(estab, today)
        payload["privatised"] = privatised
        terrace = estab.terrace_payload(today)
        payload["terrace"] = terrace
        hour = self._current_hour()
        w_end = estab.terrace_wellness_end or 17.0
        r_start = estab.terrace_restaurant_start or 18.0
        r_end = estab.terrace_restaurant_end or 23.0
        if privatised:
            mode = "restaurant"
            payload["mode_label"] = "Privatisation — service dédié au groupe"
        elif hour < w_end:
            mode = "wellness"
            payload["mode_label"] = "Mode bien-être — jusqu'à %s" % estab._float_hour_label(w_end)
        elif r_start <= hour < r_end:
            mode = "restaurant"
            payload["mode_label"] = "Mode restaurant actif"
        else:
            mode = "closed"
            payload["mode_label"] = "Service fermé"
        payload["restaurant_hours"] = "%s–%s" % (
            estab._float_hour_label(r_start),
            estab._float_hour_label(r_end),
        )
        tonight = self._reservations_in_range(
            estab.property_id.id, today, today + timedelta(days=1)
        )
        dinners = tonight.filtered(lambda r: r.meal_dinner or r.meal_lunch)
        tonight_tickets = self.env["intellix.riad.table.ticket"].search(
            [
                ("establishment_id", "=", estab.id),
                ("date", "=", today),
                ("state", "!=", "cancelled"),
            ]
        )
        ticket_by_table = {row.table_id.id: row for row in tonight_tickets}
        symbol = "€"
        prop = estab.property_id
        if prop and "currency_id" in prop._fields and prop.currency_id:
            symbol = prop.currency_id.symbol or "€"
        tables = []
        assigned = 0
        dinner_list = list(dinners)
        for table in self._active_tables(estab):
            ticket = ticket_by_table.get(table.id)
            css, label = "free", "Libre · %s" % table.seats
            guest_kind = ""
            charge_label = ""
            if ticket:
                css = "resto"
                guest_kind = ticket.guest_kind or "externe"
                charge_label = "Chambre" if ticket.charge_to_room else "Extérieur"
                label = "%s · %s · %s pers." % (
                    charge_label,
                    ticket.guest_name,
                    ticket.covers or 2,
                )
            elif table.booking_date == today and table.booking_guest:
                css, label = "resto", "%s · %s pers." % (
                    table.booking_guest,
                    table.booking_covers or 2,
                )
            elif privatised:
                css, label = "resto", "Groupe"
            elif mode == "wellness":
                css, label = "wellness", "Bien-être"
            elif mode == "restaurant" and assigned < len(dinner_list):
                resa = dinner_list[assigned]
                css = "resto"
                label = "%s pers." % self._guest_count(resa)
                assigned += 1
            tables.append(
                {
                    "id": table.id,
                    "name": table.name,
                    "css": css,
                    "label": label,
                    "seats": table.seats,
                    "zone": table.zone or "terrasse",
                    "guest_kind": guest_kind,
                    "charge_label": charge_label,
                    "ticket_id": ticket.id if ticket else False,
                    "reservation_id": ticket.reservation_id.id if ticket and ticket.reservation_id else False,
                    "guest_name": ticket.guest_name if ticket else table.booking_guest or "",
                    "covers": ticket.covers if ticket else table.booking_covers or table.seats,
                    "amount": ticket.amount if ticket else 0,
                    "tip_amount": ticket.tip_amount if ticket else 0,
                    "tip_mode": ticket.tip_mode if ticket else "cash",
                    "charge_to_room": bool(ticket.charge_to_room) if ticket else False,
                    "state": ticket.state if ticket else "",
                }
            )
        payload["tables"] = tables
        half_board = []
        dinner_price = 0.0
        if estab.property_id and "meal_dinner_price" in estab.property_id._fields:
            dinner_price = estab.property_id.meal_dinner_price or 0.0
        covers = 0
        for index, resa in enumerate(dinners):
            count = self._guest_count(resa)
            covers += count
            hour_label = "%sh%02d" % (19 + (index // 2), 30 if index % 2 else 0)
            half_board.append(
                {
                    "id": resa.id,
                    "room": resa.room_id.name or self._guest_label(resa),
                    "cover": "%s couvert%s" % (count, "s" if count > 1 else ""),
                    "time": hour_label,
                }
            )
        payload["half_board"] = half_board
        Menu = self.env["intellix.riad.menu.item"]
        payload["company"] = estab.company_id.name or ""
        payload["menu"] = Menu.payload_for_establishment(estab, kind="restaurant")
        payload["menu_now"] = Menu.payload_for_establishment(
            estab,
            kind="restaurant",
            space_mode=mode if mode in ("wellness", "restaurant") else None,
        )
        ticket_note = sum(tonight_tickets.mapped("amount"))
        ticket_tip = sum(tonight_tickets.mapped("tip_amount"))
        room_note = sum(
            t.amount for t in tonight_tickets if t.charge_to_room
        )
        amount = ticket_note or (covers * dinner_price if dinner_price else 0.0)
        payload["revenue"] = _money_label(amount, symbol) if amount else "—"
        payload["revenue_sub"] = (
            "%s couverts · %s en chambre · pourboires %s"
            % (
                covers or sum(tonight_tickets.mapped("covers")),
                _money_label(room_note, symbol) if room_note else "0" + symbol,
                _money_label(ticket_tip, symbol) if ticket_tip else "0" + symbol,
            )
        )
        payload["residents"] = [
            {
                "id": resa.id,
                "name": "%s — %s"
                % (
                    self._guest_label(resa),
                    resa.room_id.name if resa.room_id else "Séjour",
                ),
            }
            for resa in tonight
        ]
        payload["tickets"] = [
            {
                "id": row.id,
                "table": row.table_id.name or "",
                "who": row.guest_name,
                "kind": "Chambre" if row.guest_kind == "resident" else "Extérieur",
                "amount": _money_label(row.amount, symbol) if row.amount else "—",
                "tip": _money_label(row.tip_amount, symbol) if row.tip_amount else "",
                "tip_mode": "en chambre" if row.tip_mode == "room" else "comptant",
                "state": row.state,
                "state_label": dict(row._fields["state"].selection).get(row.state, ""),
            }
            for row in tonight_tickets
        ]
        return payload

    @api.model
    def get_wellness_data(self, establishment_id=None):
        payload, estab, today = self._base_screen(establishment_id)
        hours = list(range(9, 18))
        payload.update(
            {
                "hours": hours,
                "providers": [],
                "bookings": [],
                "legend": [],
            }
        )
        if not estab:
            return payload
        types = self.env["intellix.riad.wellness.type"].search([])
        payload["legend"] = [
            {"name": row.name, "css": row.css_class or "massage"} for row in types
        ]
        slots = estab.wellness_slot_ids.filtered(
            lambda s: s.state != "cancelled"
            and s.date_start
            and s.date_start.date() == today
        )
        providers = []
        for practitioner in estab.practitioner_ids.filtered("active"):
            cells = []
            for hour in hours:
                hit = next(
                    (
                        s
                        for s in slots
                        if s.practitioner_id == practitioner
                        and s.date_start
                        and s.date_start.hour == hour
                    ),
                    None,
                )
                cells.append(
                    {
                        "hour": hour,
                        "css": (
                            "b-%s" % (hit.type_id.css_class or "massage") if hit else ""
                        ),
                    }
                )
            info = self._practitioner_row(practitioner)
            providers.append(
                {
                    "id": practitioner.id,
                    "name": practitioner.name,
                    "label": info["label"],
                    "kind": info["kind"],
                    "kind_label": info["kind_label"],
                    "cells": cells,
                }
            )
        payload["providers"] = providers
        bookings = []
        for slot in slots.sorted("date_start"):
            origin = "résidente" if slot.guest_kind == "resident" else "externe"
            who = slot.guest_name or "Soin"
            if origin not in (who or "").lower():
                who = "%s — %s" % (who, origin)
            bookings.append(
                {
                    "id": slot.id,
                    "who": who,
                    "what": "%s · %s"
                    % (
                        slot.practitioner_id.name or "",
                        slot.date_start.strftime("%Hh%M") if slot.date_start else "",
                    ),
                    "type": slot.type_id.name or "",
                    "css": slot.type_id.css_class or "massage",
                }
            )
        payload["bookings"] = bookings
        payload["service_types"] = [{"id": row.id, "name": row.name} for row in types]
        payload["company"] = estab.company_id.name or ""
        payload["menu"] = self.env["intellix.riad.menu.item"].payload_for_establishment(
            estab, kind="wellness"
        )
        payload["practitioners"] = [
            self._practitioner_row(practitioner)
            for practitioner in estab.practitioner_ids.filtered("active")
        ]
        payload["staff_candidates"] = self._staff_candidates(estab)
        stays = self._reservations_in_range(
            estab.property_id.id, today, today + timedelta(days=1)
        )
        payload["residents"] = [
            {
                "id": resa.id,
                "name": (
                    resa.client_nom
                    or (resa.traveler_id.name if resa.traveler_id else False)
                    or (resa.room_id.name if resa.room_id else False)
                    or str(resa.id)
                ),
            }
            for resa in stays
        ]
        return payload

    @api.model
    def create_wellness_slot(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        vals = dict(values or {})
        offer = False
        offer_id = int(vals.pop("offer_id", 0) or 0)
        if offer_id:
            offer = self.env["intellix.riad.menu.item"].browse(offer_id)
            if (
                offer.exists()
                and offer.establishment_id == estab
                and offer.kind == "wellness"
            ):
                if offer.type_id and not vals.get("type_id"):
                    vals["type_id"] = offer.type_id.id
                if offer.price and not vals.get("amount"):
                    vals["amount"] = offer.price
        vals["establishment_id"] = estab.id
        slot = self.env["intellix.riad.wellness.slot"].create(vals)
        slot.action_confirm()
        return {"id": slot.id, "name": slot.name}

    @api.model
    def create_room_reservation(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        vals = {
            "property_id": estab.property_id.id,
            "room_id": int(values.get("room_id") or 0) or False,
            "check_in": values.get("check_in"),
            "check_out": values.get("check_out"),
            "client_nom": (values.get("guest_name") or "").strip(),
            "voyageurs": int(values.get("guests") or 2),
            "source": "direct",
            "booking_channel": "backoffice",
            "meal_breakfast": True,
        }
        if values.get("guest_residency"):
            vals["riad_guest_residency"] = values.get("guest_residency")
        if not vals["room_id"] or not vals["check_in"] or not vals["check_out"] or not vals["client_nom"]:
            raise UserError(_("Chambre, dates et nom de la cliente sont requis."))
        if "meal_breakfast" in values:
            vals["meal_breakfast"] = bool(values.get("meal_breakfast"))
        Res = self.env["coins.reservation"]
        resa = Res.create(vals)
        if hasattr(resa, "action_confirm"):
            resa.action_confirm()
        return {"id": resa.id}

    def _reservation_payload(self, resa):
        source = resa.source or ""
        channel = resa.booking_channel or ""
        if source in OTA_SOURCES or channel in OTA_CHANNELS:
            source_label = (source or channel or "OTA").capitalize()
        elif channel in SITE_CHANNELS:
            source_label = "Site du riad"
        elif channel == "backoffice" or source == "direct":
            source_label = "Saisie manuelle"
        else:
            source_label = source or channel or "—"
        state_label = dict(resa._fields["state"].selection).get(resa.state, resa.state)
        return {
            "id": resa.id,
            "is_demo": bool(resa.is_demo),
            "guest_name": self._guest_label(resa),
            "room_id": resa.room_id.id if resa.room_id else False,
            "room_name": resa.room_id.name if resa.room_id else "",
            "guests": self._guest_count(resa),
            "check_in": fields.Date.to_string(resa.check_in) if resa.check_in else "",
            "check_out": fields.Date.to_string(resa.check_out) if resa.check_out else "",
            "breakfast": bool(resa.meal_breakfast),
            "source_label": source_label,
            "state": resa.state,
            "state_label": state_label or "",
            "restaurant_note": resa.riad_restaurant_note or 0,
            "restaurant_tip": resa.riad_restaurant_tip or 0,
            "guest_residency": resa.riad_guest_residency or "unknown",
            "police_status": resa.riad_police_status or "",
            "tourist_tax_amount": resa.riad_tourist_tax_amount or 0,
            "checkin_can_send": not resa._riad_is_moroccan_guest(),
        }

    @api.model
    def get_reservation(self, establishment_id, reservation_id):
        payload, estab, _today = self._base_screen(establishment_id)
        resa = self.env["coins.reservation"].browse(int(reservation_id or 0))
        if not resa.exists():
            raise UserError(_("Réservation introuvable."))
        if estab and resa.property_id and resa.property_id != estab.property_id:
            raise UserError(_("Cette réservation n'appartient pas à cet établissement."))
        payload["reservation"] = self._reservation_payload(resa)
        payload["rooms"] = [
            {"id": room.id, "name": room.name}
            for room in (estab.property_id.room_ids.filtered("active") if estab else [])
        ]
        return payload

    @api.model
    def write_room_reservation(self, establishment_id, reservation_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        resa = self.env["coins.reservation"].browse(int(reservation_id or 0))
        if not resa.exists():
            raise UserError(_("Réservation introuvable."))
        if estab and resa.property_id and resa.property_id != estab.property_id:
            raise UserError(_("Cette réservation n'appartient pas à cet établissement."))
        vals = {
            "client_nom": (values.get("guest_name") or "").strip(),
            "room_id": int(values.get("room_id") or 0) or False,
            "check_in": values.get("check_in"),
            "check_out": values.get("check_out"),
            "voyageurs": int(values.get("guests") or 2),
            "meal_breakfast": bool(values.get("meal_breakfast")),
        }
        if values.get("guest_residency"):
            vals["riad_guest_residency"] = values.get("guest_residency")
        if not vals["room_id"] or not vals["check_in"] or not vals["check_out"] or not vals["client_nom"]:
            raise UserError(_("Chambre, dates et nom de la cliente sont requis."))
        resa.write(vals)
        return {"id": resa.id}

    @api.model
    def send_checkin_link(self, establishment_id, reservation_id):
        """Envoie le lien fiche de police — refusé si résident marocain."""
        payload, estab, _today = self._base_screen(establishment_id)
        resa = self.env["coins.reservation"].browse(int(reservation_id or 0))
        if not resa.exists():
            raise UserError(_("Réservation introuvable."))
        if estab and resa.property_id and resa.property_id != estab.property_id:
            raise UserError(_("Cette réservation n'appartient pas à cet établissement."))
        resa.action_send_checkin_link()
        return self.get_reservation(establishment_id, reservation_id)

    @api.model
    def cron_police_checkin_reminder(self):
        expired = self.env["coins.reservation"].search(
            [
                ("riad_checkin_token", "!=", False),
                ("riad_checkin_used_at", "=", False),
                ("riad_checkin_expiry", "<", fields.Datetime.now()),
            ]
        )
        if expired:
            expired.expire_checkin_token()
        return self.env["coins.reservation"].cron_police_checkin_reminder()

    @api.model
    def create_table_booking(self, establishment_id, values):
        payload, estab, today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        table = self.env["intellix.riad.table"].browse(int(values.get("table_id") or 0))
        if not table.exists() or table.establishment_id != estab:
            raise UserError(_("Choisissez une table."))
        guest_kind = values.get("guest_kind") or "externe"
        reservation = self.env["coins.reservation"].browse(
            int(values.get("reservation_id") or 0)
        )
        if guest_kind == "resident":
            if not reservation.exists():
                raise UserError(_("Liez la table à un séjour pour une résidente."))
            if estab.property_id and reservation.property_id != estab.property_id:
                raise UserError(_("Ce séjour n'appartient pas à cet établissement."))
            guest = (values.get("guest_name") or "").strip() or self._guest_label(reservation)
        else:
            reservation = self.env["coins.reservation"]
            guest = (values.get("guest_name") or "").strip()
            if not guest:
                raise UserError(_("Indiquez le nom de la cliente extérieure."))
        day = values.get("date") or today
        amount = float(values.get("amount") or 0)
        tip_amount = float(values.get("tip_amount") or 0)
        charge_to_room = bool(values.get("charge_to_room")) and guest_kind == "resident"
        tip_mode = values.get("tip_mode") or "cash"
        if charge_to_room and tip_amount and tip_mode != "cash":
            tip_mode = "room"
        if not charge_to_room:
            tip_mode = "cash"
        vals = {
            "establishment_id": estab.id,
            "table_id": table.id,
            "date": day,
            "guest_kind": guest_kind,
            "reservation_id": reservation.id if reservation else False,
            "guest_name": guest,
            "covers": int(values.get("covers") or 2),
            "amount": amount,
            "tip_amount": tip_amount,
            "tip_mode": tip_mode,
            "charge_to_room": charge_to_room,
        }
        Ticket = self.env["intellix.riad.table.ticket"]
        ticket = Ticket.browse(int(values.get("ticket_id") or 0))
        if ticket.exists() and ticket.establishment_id == estab:
            if ticket.state == "charged" and not charge_to_room:
                raise UserError(_("Cette note est déjà poussée en chambre."))
            ticket.write(vals)
        else:
            existing = Ticket.search(
                [
                    ("table_id", "=", table.id),
                    ("date", "=", day),
                    ("state", "!=", "cancelled"),
                ],
                limit=1,
            )
            ticket = existing
            if ticket:
                ticket.write(vals)
            else:
                ticket = Ticket.create(vals)
        table.write(
            {
                "booking_guest": guest,
                "booking_covers": ticket.covers,
                "booking_date": day,
            }
        )
        if charge_to_room and (amount or tip_amount):
            ticket.action_charge_to_room()
        elif amount and guest_kind == "externe":
            ticket.state = "paid"
        return {"id": table.id, "ticket_id": ticket.id, "state": ticket.state}

    @api.model
    def create_event(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        name = (values.get("name") or "").strip()
        if not name:
            raise UserError(_("Donnez un nom à l'événement."))
        day_start = values.get("day_start") or values.get("check_in")
        day_end = values.get("day_end") or values.get("check_out") or day_start
        vals = {
            "establishment_id": estab.id,
            "name": name,
            "day_start": day_start,
            "day_end": day_end,
            "guest_count": int(values.get("guest_count") or values.get("guests") or 0),
            "checklist_kind": values.get("checklist_kind") or "none",
            "event_kind": values.get("event_kind") or "other",
            "is_full_privatisation": bool(values.get("is_full_privatisation")),
            "include_half_board": bool(values.get("include_half_board")),
        }
        if day_start:
            vals["date_start"] = fields.Datetime.to_datetime("%s 10:00:00" % day_start)
        event = self.env["intellix.riad.event"].create(vals)
        return {"id": event.id, "name": event.name}

    @api.model
    def create_privatisation(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        name = (values.get("name") or values.get("guest_name") or "").strip()
        if not name:
            raise UserError(_("Indiquez le nom du groupe."))
        start = values.get("date_start") or values.get("check_in")
        end = values.get("date_end") or values.get("check_out") or start
        if start and end:
            start_d = fields.Date.to_date(start)
            end_d = fields.Date.to_date(end)
            if end_d > start_d:
                end_d = end_d - timedelta(days=1)
            if end_d < start_d:
                end_d = start_d
            start, end = fields.Date.to_string(start_d), fields.Date.to_string(end_d)
        priv = self.env["intellix.riad.privatisation"].create(
            {
                "establishment_id": estab.id,
                "name": name,
                "date_start": start,
                "date_end": end,
                "guest_count": int(values.get("guest_count") or values.get("guests") or 0),
            }
        )
        try:
            priv.action_confirm()
        except UserError as err:
            return {
                "id": priv.id,
                "state": priv.state,
                "warning": err.args[0] if err.args else str(err),
            }
        return {"id": priv.id, "state": priv.state}

    @api.model
    def create_staff(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        name = (values.get("name") or "").strip()
        if not name:
            raise UserError(_("Indiquez le nom de l'employé."))
        role_id = int(values.get("role_id") or 0)
        if not estab.company_id:
            estab._ensure_anna_sweety_company()
        vals = {
            "riad_establishment_id": estab.id,
            "riad_new_employee_name": name,
            "riad_phone": values.get("phone") or False,
            "riad_hire_date": values.get("hire_date") or False,
            "work_email": values.get("email") or False,
        }
        if role_id:
            vals["riad_role_ids"] = [(4, role_id)]
        profile = self.env["pe.employee.profile"].create(vals)
        return {"id": profile.id, "name": profile.display_name}

    @api.model
    def get_events_data(self, establishment_id=None, bucket=None):
        payload, estab, today = self._base_screen(establishment_id)
        payload.update(
            {
                "events": [],
                "counts": {"upcoming": 0, "current": 0, "past": 0},
                "checklist_kinds": [
                    {"id": key, "name": label} for key, label in CHECKLIST_KINDS
                ],
            }
        )
        if not estab:
            return payload
        events = estab.event_ids.filtered(lambda e: e.state != "cancelled")
        rows = []
        counts = {"upcoming": 0, "current": 0, "past": 0}
        for event in events.sorted("date_start"):
            start = event.date_start.date() if event.date_start else today
            end = event.date_end.date() if event.date_end else start
            if start <= today <= end:
                kind = "current"
            elif start > today:
                kind = "upcoming"
            else:
                kind = "past"
            counts[kind] += 1
            total = event.task_total_count or 0
            done = event.task_done_count or 0
            pct = int(round(100.0 * done / total)) if total else 0
            bits = []
            if event.guest_count:
                bits.append("%s personnes" % event.guest_count)
            rooms = len(event.reservation_ids)
            if rooms:
                bits.append("%s chambre%s" % (rooms, "s" if rooms > 1 else ""))
            if event.template_id:
                bits.append("Modèle : %s" % event.template_id.name)
            rows.append(
                {
                    "id": event.id,
                    "bucket": kind,
                    "date_chip": "%s %s" % (start.day, MONTHS_FR[start.month][:4] + "."),
                    "title": event.name,
                    "sub": " · ".join(bits) or (event.notes or ""),
                    "pct": pct,
                    "progress": "%s/%s tâches" % (done, total) if total else "0 tâche",
                }
            )
        payload["events"] = rows
        payload["counts"] = counts
        return payload

    @api.model
    def get_event_detail(self, establishment_id=None, event_id=None):
        payload, estab, today = self._base_screen(establishment_id)
        payload.update({"event": False, "columns": []})
        if not event_id:
            return payload
        event = self.env["intellix.riad.event"].browse(int(event_id))
        if not event.exists():
            return payload
        start = event.date_start.date() if event.date_start else today
        end = event.date_end.date() if event.date_end else start
        period = "%s–%s %s %s" % (
            start.day,
            end.day,
            MONTHS_FR[start.month],
            start.year,
        )
        meal = (
            dict(event._fields["meal_plan"].selection).get(event.meal_plan)
            if event.meal_plan
            else "—"
        )
        payload["event"] = {
            "id": event.id,
            "name": event.name,
            "sub": "%s · %s personnes · %s"
            % (
                period,
                event.guest_count or 0,
                event.template_id.name or "Sans modèle",
            ),
            "template": event.template_id.name or "",
            "summary": [
                {"value": str(len(event.reservation_ids)), "label": "Chambres"},
                {"value": meal, "label": "Restaurant"},
                {
                    "value": str(len(event.wellness_slot_ids)),
                    "label": "Session bien-être",
                },
                {
                    "value": event.task_progress_label,
                    "label": "Tâches complétées",
                },
            ],
        }
        labels = {"todo": "À faire", "doing": "En cours", "done": "Fait"}
        columns = []
        for key in ("todo", "doing", "done"):
            cards = []
            for task in event.task_ids.filtered(lambda t: t.state == key):
                due = ""
                if task.date_deadline:
                    due = (
                        "Retard — %s %s"
                        % (task.date_deadline.day, MONTHS_FR[task.date_deadline.month][:4])
                        if task.is_late
                        else "%s %s"
                        % (task.date_deadline.day, MONTHS_FR[task.date_deadline.month][:4])
                    )
                cards.append(
                    {
                        "id": task.id,
                        "name": task.name,
                        "initial": task.assignee_initial or "?",
                        "due": due,
                        "late": bool(task.is_late),
                    }
                )
            columns.append({"key": key, "label": labels[key], "cards": cards})
        payload["columns"] = columns
        return payload

    @api.model
    def get_personnel_data(self, establishment_id=None):
        payload, estab, today = self._base_screen(establishment_id)
        payload.update(
            {
                "staff": [],
                "report_title": "Rapport de paie",
                "report_sub": "Généré automatiquement, envoyé au comptable le 1er de chaque mois",
            }
        )
        if not estab:
            return payload
        attendance = {row["id"]: row for row in self._attendance_today(estab, today)}
        compiled = {
            row["name"]: row for row in estab.compile_payroll_rows(today.year, today.month)
        }
        staff = []
        for profile in estab._riad_staff_profiles():
            name = profile.display_name or profile.employee_id.name or ""
            today_row = attendance.get(profile.id) or {}
            month = compiled.get(name) or {}
            staff.append(
                {
                    "id": profile.id,
                    "name": name,
                    "initial": (name[:1] or "?").upper(),
                    "role": today_row.get("role") or profile.riad_role_label(),
                    "company": profile.company_id.name
                    or (profile.employee_company_id.name or ""),
                    "establishment": profile.riad_establishment_id.name or "",
                    "phone": profile.riad_phone or profile.work_phone or "",
                    "email": profile.work_email or "",
                    "hire_date": fields.Date.to_string(profile.riad_hire_date)
                    if profile.riad_hire_date
                    else "",
                    "status": today_row.get("status") or "Non pointé",
                    "what": today_row.get("what") or "Non pointé",
                    "css": today_row.get("css") or "muted",
                    "kind": today_row.get("kind"),
                    "locked": today_row.get("locked"),
                    "punched": today_row.get("punched"),
                    "summary_id": today_row.get("summary_id"),
                    "days": month.get("days_worked", 0),
                    "absences": (
                        month.get("absences_planned", 0)
                        + month.get("absences_unplanned", 0)
                        + month.get("leave_days", 0)
                    ),
                }
            )
        payload["staff"] = staff
        Menu = self.env["intellix.riad.menu.item"]
        payload["company"] = estab.company_id.name or ""
        payload["wellness_menu"] = Menu.payload_for_establishment(estab, kind="wellness")
        payload["restaurant_menu"] = Menu.payload_for_establishment(
            estab, kind="restaurant"
        )
        payload["staff_roles"] = [
            {"id": role.id, "name": role.name}
            for role in self.env["intellix.riad.staff.role"].search([], order="sequence")
        ]
        payload["report_title"] = "Rapport de paie — %s %s" % (
            MONTHS_FR[today.month],
            today.year,
        )
        return payload

    @api.model
    def punch_today(self, profile_id, kind, arrival=None, day=None):
        profile = self.env["pe.employee.profile"].browse(int(profile_id))
        if not profile.exists():
            raise UserError("Fiche employé introuvable.")
        profile.riad_punch(kind, arrival=arrival or None, day=day)
        return True

    @api.model
    def get_staff_detail(self, establishment_id=None, profile_id=None):
        payload, estab, today = self._base_screen(establishment_id)
        payload.update({"staff_detail": False})
        if not estab or not profile_id:
            return payload
        profile = self.env["pe.employee.profile"].browse(int(profile_id))
        if not profile.exists() or profile.riad_establishment_id != estab:
            return payload
        name = profile.display_name or profile.employee_id.name or ""
        start = today.replace(day=1)
        last = today.replace(day=monthrange(today.year, today.month)[1])
        summaries = self.env["pe.presence.summary"].search(
            [
                ("employee_id", "=", profile.employee_id.id),
                ("date", ">=", start),
                ("date", "<=", last),
            ],
            order="date desc",
        )
        by_day = {row.date: row for row in summaries}
        days = []
        cursor = last
        while cursor >= start:
            row = by_day.get(cursor)
            locked = bool(
                row
                and row.riad_locked
                or self.env["pe.presence.summary"]._month_is_locked(estab, cursor)
            )
            days.append(
                {
                    "date": fields.Date.to_string(cursor),
                    "date_label": "%s %s %s"
                    % (WEEKDAYS_LONG[cursor.weekday()], cursor.day, MONTHS_FR[cursor.month]),
                    "summary_id": row.id if row else False,
                    "status": row.riad_status_label() if row else "Non pointé",
                    "css": row.riad_status_css() if row else "muted",
                    "kind": row.riad_kind() if row else False,
                    "locked": locked,
                    "corrections": [
                        {
                            "id": corr.id,
                            "when": fields.Datetime.context_timestamp(
                                self, corr.changed_at
                            ).strftime("%d/%m %Hh%M")
                            if corr.changed_at
                            else "",
                            "who": corr.changed_by_id.name or "",
                            "previous": corr.previous_label or "",
                            "new": corr.new_label or "",
                        }
                        for corr in (row.riad_correction_ids if row else [])
                    ],
                }
            )
            cursor -= timedelta(days=1)
        payload["staff_detail"] = {
            "id": profile.id,
            "name": name,
            "initial": (name[:1] or "?").upper(),
            "role": profile.riad_role_label(),
            "company": profile.company_id.name
            or (profile.employee_company_id.name or ""),
            "establishment": profile.riad_establishment_id.name or "",
            "phone": profile.riad_phone or profile.work_phone or "",
            "email": profile.work_email or "",
            "hire_date": fields.Date.to_string(profile.riad_hire_date)
            if profile.riad_hire_date
            else "",
            "days": days,
        }
        return payload

    @api.model
    def get_settings_data(self, establishment_id=None):
        payload, estab, _today = self._base_screen(establishment_id)
        payload.update(
            {
                "tables": [],
                "rooms": [],
                "practitioners": [],
                "service_types": [],
                "zones": [
                    {"id": "terrasse", "name": "Terrasse"},
                    {"id": "patio", "name": "Patio"},
                    {"id": "salon", "name": "Salon"},
                ],
                "settings": {},
            }
        )
        types = self.env["intellix.riad.wellness.type"].search([])
        payload["service_types"] = [{"id": row.id, "name": row.name} for row in types]
        if not estab:
            return payload
        payload["tables"] = [
            {
                "id": table.id,
                "name": table.name,
                "seats": table.seats,
                "zone": table.zone or "terrasse",
            }
            for table in self._active_tables(estab)
        ]
        payload["rooms"] = [
            {
                "id": room.id,
                "name": room.name,
                "emplacement": room.emplacement or "etage",
                "price_per_night": room.price_per_night or 0,
            }
            for room in estab.property_id.room_ids.filtered("active")
        ]
        payload["practitioners"] = [
            self._practitioner_row(row)
            for row in estab.practitioner_ids.filtered("active")
        ]
        payload["staff_candidates"] = self._staff_candidates(estab)
        Menu = self.env["intellix.riad.menu.item"]
        payload["company"] = estab.company_id.name or ""
        payload["wellness_menu"] = Menu.payload_for_establishment(estab, kind="wellness")
        payload["restaurant_menu"] = Menu.payload_for_establishment(
            estab, kind="restaurant"
        )
        payload["settings"] = {
            "terrace_enabled": bool(estab.terrace_enabled),
            "terrace_wellness_start": _hour_to_input(estab.terrace_wellness_start),
            "terrace_wellness_end": _hour_to_input(estab.terrace_wellness_end),
            "terrace_restaurant_start": _hour_to_input(estab.terrace_restaurant_start),
            "terrace_restaurant_end": _hour_to_input(estab.terrace_restaurant_end),
            "terrace_wellness_label": estab.terrace_wellness_label or "",
            "terrace_restaurant_label": estab.terrace_restaurant_label or "",
            "payroll_accountant_name": estab.payroll_accountant_name or "",
            "payroll_accountant_email": estab.payroll_accountant_email or "",
        }
        return payload

    @api.model
    def get_channels_data(self, establishment_id=None):
        """Connexion Channex + plateformes OTA pour l'établissement courant."""
        payload, estab, _today = self._base_screen(establishment_id)
        payload["channex"] = {
            "mapped": False,
            "channex_id": "",
            "status": "disconnected",
            "status_label": _("Pas encore lié à Channex"),
            "last_sync": False,
            "last_error": False,
            "note": _(
                "Coins Marocain crée la propriété dans Channex, puis vous connectez "
                "Booking / Airbnb depuis VOTRE extranet (2FA sur votre téléphone)."
            ),
        }
        payload["platforms"] = []
        payload["can_refresh"] = False
        if not estab or not estab.property_id:
            return payload

        Mapping = self.env["coins.channex.mapping"].sudo()
        mapping = Mapping.search(
            [
                ("kind", "=", "property"),
                ("property_id", "=", estab.property_id.id),
            ],
            limit=1,
        )
        Push = self.env["coins.channex.push"].sudo()
        Calendar = self.env["coins.channex.calendar"].sudo()
        last_ok = Push.search(
            [("property_id", "=", estab.property_id.id), ("state", "=", "done")],
            order="write_date desc",
            limit=1,
        )
        last_cal = Calendar.search(
            [("property_id", "=", estab.property_id.id), ("state", "=", "done")],
            order="write_date desc",
            limit=1,
        )
        last_err = Push.search(
            [("property_id", "=", estab.property_id.id), ("state", "=", "error")],
            order="write_date desc",
            limit=1,
        )
        last_sync = False
        for when in (
            last_ok.write_date if last_ok else False,
            last_cal.write_date if last_cal else False,
        ):
            if when and (not last_sync or when > last_sync):
                last_sync = when

        if mapping and (mapping.channex_id or "").strip():
            status, status_label = "active", _("Lié à Channex")
            if last_err and (not last_sync or last_err.write_date > last_sync):
                status, status_label = "error", _("Erreur de sync récente")
            payload["channex"] = {
                "mapped": True,
                "channex_id": mapping.channex_id,
                "status": status,
                "status_label": status_label,
                "last_sync": fields.Datetime.to_string(last_sync) if last_sync else False,
                "last_error": (last_err.error_message or False) if last_err else False,
                "note": _(
                    "Propriété synchronisée via Channex. Connectez ensuite chaque "
                    "plateforme OTA avec les guides officiels ci-dessous."
                ),
            }
            payload["can_refresh"] = True

        payload["platforms"] = estab.sudo().portal_ota_rows()
        return payload

    @api.model
    def mark_ota_pending(self, establishment_id, codes):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            return payload
        estab.sudo().apply_portal_ota_pending(codes or [])
        return self.get_channels_data(estab.id)

    @api.model
    def refresh_ota_from_channex(self, establishment_id=None):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            return payload
        try:
            estab.sudo().action_refresh_ota_statuses_from_channex()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("refresh OTA from Channex")
            payload = self.get_channels_data(estab.id)
            payload["refresh_error"] = str(exc)
            return payload
        return self.get_channels_data(estab.id)

    @api.model
    def get_finance_data(self, establishment_id=None):
        payload, estab, _today = self._base_screen(establishment_id)
        payload["billing"] = {}
        payload["performance"] = {}
        if not estab:
            return payload
        payload["billing"] = estab.sudo().portal_billing_payload()
        payload["performance"] = estab.sudo().portal_performance_payload()
        return payload

    @api.model
    def get_whatsapp_data(self, establishment_id=None):
        payload, estab, _today = self._base_screen(establishment_id)
        payload["whatsapp"] = {}
        payload["items"] = []
        if not estab:
            return payload
        rows = [r for r in estab.sudo().portal_ota_rows() if r.get("code") == "whatsapp"]
        payload["whatsapp"] = rows[0] if rows else {
            "status": "not_connected",
            "status_label": _("Non provisionné"),
            "messaging_label": _("Numéro WhatsApp Business dédié à ce lieu — pas encore branché."),
        }
        payload["items"] = self._thread_items(estab, ("whatsapp",), limit=40)
        for row in payload["items"]:
            row["icon"] = "WA"
            row["css"] = "ico-whatsapp"
            row["kind"] = "whatsapp"
        return payload

    @api.model
    def save_settings(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        vals = values or {}
        estab.write(
            {
                "terrace_wellness_start": _input_to_hour(vals.get("terrace_wellness_start")),
                "terrace_wellness_end": _input_to_hour(vals.get("terrace_wellness_end")),
                "terrace_restaurant_start": _input_to_hour(
                    vals.get("terrace_restaurant_start")
                ),
                "terrace_restaurant_end": _input_to_hour(vals.get("terrace_restaurant_end")),
                "terrace_wellness_label": vals.get("terrace_wellness_label") or False,
                "terrace_restaurant_label": vals.get("terrace_restaurant_label") or False,
                "payroll_accountant_name": vals.get("payroll_accountant_name") or False,
                "payroll_accountant_email": vals.get("payroll_accountant_email") or False,
            }
        )
        return {"id": estab.id}

    @api.model
    def save_floor_plan(self, establishment_id, tables):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        Table = self.env["intellix.riad.table"]
        keep_ids = []
        for index, row in enumerate(tables or []):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            vals = {
                "establishment_id": estab.id,
                "name": name,
                "seats": max(int(row.get("seats") or 2), 1),
                "zone": row.get("zone") or "terrasse",
                "sequence": (index + 1) * 10,
                "active": True,
            }
            record = Table.browse(int(row.get("id") or 0))
            if record.exists() and record.establishment_id == estab:
                record.write(vals)
            else:
                record = Table.create(vals)
            keep_ids.append(record.id)
        leftovers = self._active_tables(estab).filtered(lambda t: t.id not in keep_ids)
        leftovers.write({"active": False})
        return {"ids": keep_ids}

    @api.model
    def create_practitioner(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        kind = values.get("kind") or "external"
        profile = self.env["pe.employee.profile"].browse(int(values.get("staff_id") or 0))
        if profile.exists():
            if estab and profile.riad_establishment_id != estab:
                raise UserError(_("Cette fiche personnel n'appartient pas à cet établissement."))
            kind = "staff"
            name = (values.get("name") or "").strip() or (
                profile.display_name
                or (profile.employee_id.name if profile.employee_id else "")
                or ""
            )
        else:
            profile = self.env["pe.employee.profile"]
            name = (values.get("name") or "").strip()
        if not name:
            raise UserError(_("Indiquez le nom de la personne."))
        type_ids = [int(tid) for tid in (values.get("type_ids") or []) if tid]
        practitioner = self.env["intellix.riad.practitioner"].create(
            {
                "establishment_id": estab.id,
                "name": name,
                "kind": kind if kind in ("staff", "external") else "external",
                "pe_profile_id": profile.id if profile else False,
                "type_ids": [(6, 0, type_ids)],
            }
        )
        if profile:
            profile.riad_practitioner_id = practitioner.id
        return {"id": practitioner.id, "name": practitioner.name, "kind": practitioner.kind}

    @api.model
    def create_room(self, establishment_id, values):
        payload, estab, _today = self._base_screen(establishment_id)
        if not estab:
            raise UserError(_("Choisissez un établissement."))
        name = (values.get("name") or "").strip()
        if not name:
            raise UserError(_("Indiquez le nom de la chambre."))
        Room = self.env["coins.property.room"]
        vals = {
            "property_id": estab.property_id.id,
            "name": name,
        }
        if "emplacement" in Room._fields:
            vals["emplacement"] = values.get("emplacement") or "etage"
        if "price_per_night" in Room._fields:
            vals["price_per_night"] = float(values.get("price_per_night") or 0)
        if "breakfast_included" in Room._fields:
            vals["breakfast_included"] = True
        try:
            room = Room.create(vals)
        except Exception:
            room = Room.sudo().create(vals)
        return {"id": room.id, "name": room.name}
