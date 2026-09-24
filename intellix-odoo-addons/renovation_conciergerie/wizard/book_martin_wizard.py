# -*- coding: utf-8 -*-
from collections import OrderedDict
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from ..models.reno_rdv_tz import (
    RENO_CANADA_TZ,
    RENO_MARTIN_CALENDAR_COLOR,
    RENO_MARTIN_LOGIN,
    RENO_SLOT_HOURS,
    RENO_SLOT_MINUTES,
    reno_parse_utc_slot,
    reno_toronto_wall_to_utc,
)


class RenovationBookMartinWizard(models.TransientModel):
    """Réunions partenaires Réno → calendrier Martin uniquement.

    Créneaux widget = UTC (grille America/Toronto).
    Hors créneau = mur America/Toronto, jamais le TZ de Leila (Lagos)
    ni de Karine (Casablanca) — c'est le bug 9h / 3h du matin.
    """

    _name = "renovation.book.martin.wizard"
    _description = "Planifier une réunion Réno Immobilier (Martin)"

    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire",
        ondelete="cascade",
    )
    lead_id = fields.Many2one(
        "crm.lead",
        string="Fiche lead",
        ondelete="cascade",
    )
    slot = fields.Char(string="Créneau")
    start_toronto = fields.Char(
        string="Hors créneau (heure du Canada)",
        help="Format 2026-09-15 09:00 — heure de Toronto, pas votre fuseau.",
    )
    note = fields.Text(string="Note pour Martin")
    contact_name = fields.Char(string="Contact")
    phone = fields.Char(string="Téléphone")
    email_from = fields.Char(string="Email")

    def onchange(self, values, field_names, fields_spec):
        known = set(self._fields)
        values = {k: v for k, v in (values or {}).items() if k in known or k == "id"}
        field_names = [n for n in (field_names or []) if n in known]
        fields_spec = {k: v for k, v in (fields_spec or {}).items() if k in known}
        return super().onchange(values, field_names, fields_spec)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        partner = False
        pid = res.get("partner_id") or self.env.context.get("default_partner_id")
        lid = res.get("lead_id") or self.env.context.get("default_lead_id")
        if pid:
            partner = self.env["res.partner"].browse(pid)
        elif lid:
            lead = self.env["crm.lead"].browse(lid)
            if lead.exists():
                res["contact_name"] = lead.contact_name or lead.partner_name or False
                res["phone"] = lead.phone or False
                res["email_from"] = lead.email_from or False
                if lead.partner_id:
                    res["partner_id"] = lead.partner_id.id
                    partner = lead.partner_id
        if partner and partner.exists():
            res.setdefault("contact_name", partner.name)
            res.setdefault("phone", partner.phone or partner.mobile)
            res.setdefault("email_from", partner.email)
        return res

    @api.model
    def _reno_martin_host(self):
        host = self.env["res.users"].sudo().search(
            [("login", "=", RENO_MARTIN_LOGIN)], limit=1
        )
        if not host:
            raise UserError(
                _("Compte Martin introuvable (%s).") % RENO_MARTIN_LOGIN
            )
        return host

    @api.model
    def get_slots_ui(self):
        Event = self.env["calendar.event"].sudo()
        if hasattr(Event, "doorway_martin_slots_ui"):
            return Event.doorway_martin_slots_ui()
        return self._reno_martin_slots_ui_fallback()

    @api.model
    def _reno_martin_slots_ui_fallback(self):
        user = self._reno_martin_host()
        tz = pytz.timezone(RENO_CANADA_TZ)
        now = datetime.now(tz)
        Event = self.env["calendar.event"].sudo()
        slots = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for _ in range(30):
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for hour in RENO_SLOT_HOURS:
                for minute in (0, 30):
                    slot_local = day.replace(hour=hour, minute=minute)
                    if slot_local <= now:
                        continue
                    slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    if Event.search_count(self._reno_busy_domain(user, slot_utc)):
                        continue
                    slots.append((slot_utc, slot_local))
                    if len(slots) >= 400:
                        break
                if len(slots) >= 400:
                    break
            if len(slots) >= 400:
                break
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
                    "label": "%s %s %s" % (
                        wd, slot_local.day, months_fr[slot_local.month - 1]
                    ),
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

    def _reno_busy_domain(self, user, slot_utc, minutes=RENO_SLOT_MINUTES):
        Event = self.env["calendar.event"].sudo()
        if hasattr(Event, "doorway_martin_busy_domain"):
            return Event.doorway_martin_busy_domain(user, slot_utc, minutes=minutes)
        return [
            "|",
            ("user_id", "=", user.id),
            ("partner_ids", "in", [user.partner_id.id]),
            ("start", "<", slot_utc + timedelta(minutes=minutes)),
            ("stop", ">", slot_utc),
        ]

    def _reno_event_title(self, partner, lead):
        if partner:
            return "RDV %s — Martin (Réno Immobilier)" % (partner.name or "partenaire")
        contact = (lead.contact_name or lead.partner_name or "").strip() if lead else ""
        etab = (lead.name or "partenaire").strip() if lead else "partenaire"
        if contact and contact != etab:
            return "RDV %s — %s — Martin (Réno Immobilier)" % (contact, etab)
        return "RDV %s — Martin (Réno Immobilier)" % etab

    def _reno_contact_block_html(self, partner, lead):
        lines = []
        if partner:
            lines.append("Partenaire : %s" % (partner.name or ""))
            phones = [
                (partner.phone or "").strip(),
                (getattr(partner, "mobile", None) or "").strip(),
            ]
            if any(phones):
                lines.append(
                    "Téléphones : %s" % " ; ".join(x for x in phones if x)
                )
            addr = ", ".join(
                x
                for x in [
                    (partner.street or "").strip(),
                    (partner.city or "").strip(),
                    (partner.zip or "").strip(),
                ]
                if x
            )
            if addr:
                lines.append("Adresse : %s" % addr)
            if partner.email:
                lines.append("Email : %s" % partner.email)
        elif lead:
            contact = (lead.contact_name or lead.partner_name or "").strip()
            if contact:
                lines.append("Contact : %s" % contact)
            if lead.phone:
                lines.append("Téléphones : %s" % lead.phone)
            if lead.email_from:
                lines.append("Email : %s" % lead.email_from)
        if self.contact_name:
            lines.append("Contact saisi : %s" % self.contact_name)
        return "<br/>".join(html_escape(line) for line in lines)

    def _reno_resolve_start_utc(self):
        """Widget = UTC. Hors créneau = mur Toronto → UTC."""
        if self.slot:
            return reno_parse_utc_slot(self.slot)
        if self.start_toronto:
            return reno_toronto_wall_to_utc(self.start_toronto)
        raise UserError(_("Choisissez un jour, puis une heure."))

    def action_confirm(self):
        self.ensure_one()
        if not self.partner_id and not self.lead_id:
            raise UserError(_("Indiquez le partenaire (ou la fiche lead)."))
        martin = self._reno_martin_host()
        start = self._reno_resolve_start_utc()
        Event = self.env["calendar.event"].sudo()
        if Event.search_count(self._reno_busy_domain(martin, start)):
            raise UserError(
                _("Ce créneau vient d'être pris — choisissez-en un autre.")
            )
        stop = start + timedelta(minutes=RENO_SLOT_MINUTES)
        partner = self.partner_id
        lead = self.lead_id
        booker = self.env.user
        # Martin + booker seulement — pas d'invitation e-mail au partenaire B2B.
        attendees = [(4, martin.partner_id.id)]
        if booker.partner_id.id != martin.partner_id.id:
            attendees.append((4, booker.partner_id.id))
        desc_bits = [
            html_escape("Réno Immobilier — réunion partenariat"),
            html_escape("Hôte calendrier : Martin Houle."),
            html_escape("Booké par : %s" % (booker.name or "")),
        ]
        contact_html = self._reno_contact_block_html(partner, lead)
        if contact_html:
            desc_bits.append(contact_html)
        if self.note:
            desc_bits.append(
                html_escape(self.note.strip()).replace("\n", "<br/>")
            )
        if partner:
            model = self.env["ir.model"].sudo()._get("res.partner")
            res_id = partner.id
        else:
            model = self.env["ir.model"].sudo()._get("crm.lead")
            res_id = lead.id
        event_vals = {
            "name": self._reno_event_title(partner, lead),
            "start": start,
            "stop": stop,
            "user_id": martin.id,
            "event_tz": RENO_CANADA_TZ,
            "partner_ids": attendees,
            "res_id": res_id,
            "description": "<br/>".join(desc_bits),
        }
        if model:
            event_vals["res_model_id"] = model.id
        if lead:
            event_vals["opportunity_id"] = lead.id
        if "color" in Event._fields and not Event._fields["color"].compute:
            event_vals["color"] = RENO_MARTIN_CALENDAR_COLOR
        event = Event.create(event_vals)
        if martin.partner_id and martin.partner_id.color != RENO_MARTIN_CALENDAR_COLOR:
            try:
                martin.partner_id.sudo().write({"color": RENO_MARTIN_CALENDAR_COLOR})
            except Exception:
                pass
        rdv = self.env["renovation.partner.rdv"].sudo().create(
            {
                "partner_id": partner.id if partner else False,
                "lead_id": lead.id if lead else False,
                "booker_id": booker.id,
                "martin_user_id": martin.id,
                "start_at": start,
                "stop_at": stop,
                "event_id": event.id,
                "note": (self.note or "").strip() or False,
                "state": "booked",
                "event_tz": RENO_CANADA_TZ,
            }
        )
        if partner:
            partner.sudo()._reno_crm_mark_rdv_pris(event)
            if not partner.reno_crm_user_id:
                partner.sudo().write({"reno_crm_user_id": booker.id})
            self.env["renovation.partner.interaction"].sudo().create(
                {
                    "partner_id": partner.id,
                    "kind": "rdv",
                    "summary": "RDV Martin %s (booké par %s)"
                    % (rdv.start_at_display or "", booker.name or ""),
                    "body": (self.note or "").strip() or False,
                    "user_id": booker.id,
                    "rdv_id": rdv.id,
                }
            )
        if lead:
            lead.sudo().write({"reno_rdv_event_id": event.id})
        return {
            "type": "ir.actions.act_window_close",
            "context": {"reno_rdv_id": rdv.id, "reno_event_id": event.id},
        }
