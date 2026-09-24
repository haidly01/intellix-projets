# -*- coding: utf-8 -*-
import logging

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools import html2plaintext
from html import unescape

DOORWAY_CANADA_TZ = "America/Toronto"
DOORWAY_MARTIN_LOGIN = "martin@agencedoorway.com"
_WEEKDAYS_FR = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
_MONTHS_FR = (
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
)


def doorway_format_canada(dt):
    """UTC naïf Odoo → libellé heure du Canada (America/Toronto)."""
    if not dt:
        return ""
    tz = pytz.timezone(DOORWAY_CANADA_TZ)
    if getattr(dt, "tzinfo", None):
        local = dt.astimezone(tz)
    else:
        local = pytz.UTC.localize(dt).astimezone(tz)
    return "%s %s %s %s à %sh%s (heure du Canada)" % (
        _WEEKDAYS_FR[local.weekday()],
        local.day,
        _MONTHS_FR[local.month - 1],
        local.year,
        local.strftime("%H"),
        local.strftime("%M"),
    )

from .mail_activity import (
    DOORWAY_SYNC_MODELS,
    SKIP_ACTIVITY_SYNC_CTX,
    SKIP_CALENDAR_SYNC_CTX,
)

_logger = logging.getLogger(__name__)


class DoorwayCalendarEvent(models.Model):
    _inherit = "calendar.event"

    def _sync_activities(self, fields=None):
        if self.env.context.get(SKIP_ACTIVITY_SYNC_CTX):
            return
        return super()._sync_activities(fields=fields)

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
            if res_id:
                defaults["res_id"] = res_id
            if "opportunity_id" in defaults:
                defaults["opportunity_id"] = False
        return defaults

    def _doorway_linked_record(self):
        """Ne jamais mapper un res_id nu vers crm.lead (collision d'ids CQ)."""
        self.ensure_one()
        model = self.res_model
        res_id = self.res_id
        if "coins.quebec.partenariat" in self.env:
            part = self.env["coins.quebec.partenariat"].sudo().search(
                [("cq_rdv_event_id", "=", self.id)], limit=1
            )
            if part:
                return part
        if model == "coins.quebec.partenariat" and res_id and model in self.env:
            rec = self.env[model].sudo().browse(res_id)
            return rec if rec.exists() else rec.browse()
        if model == "crm.lead" and res_id:
            rec = self.env["crm.lead"].sudo().browse(res_id)
            return rec if rec.exists() else rec.browse()
        if (
            "opportunity_id" in self._fields
            and self.opportunity_id
            and model in (False, "crm.lead")
        ):
            return self.opportunity_id
        if model in DOORWAY_SYNC_MODELS and res_id and model in self.env:
            rec = self.env[model].sudo().browse(res_id)
            return rec if rec.exists() else rec.browse()
        return self.env["crm.lead"].browse()

    def _doorway_ensure_activity_from_event(self, post_note=False):
        """Calendrier → activité du commercial + note sur la fiche liée."""
        if self.env.context.get(SKIP_ACTIVITY_SYNC_CTX):
            return
        Activity = self.env["mail.activity"].sudo().with_context(
            **{SKIP_CALENDAR_SYNC_CTX: True}
        )
        for event in self:
            record = event._doorway_linked_record()
            if not record:
                continue
            activity = event.activity_ids[:1]
            if not activity:
                activity = Activity.search(
                    [("calendar_event_id", "=", event.id)], limit=1
                )
            start = event.start
            vals = {
                "summary": event.name or "",
                "note": event.description or "",
                "date_deadline": (
                    fields.Date.to_date(start)
                    if start
                    else fields.Date.context_today(event)
                ),
                "user_id": event.user_id.id or self.env.user.id,
                "doorway_scheduled_start": start,
            }
            if event.stop and start:
                delta = event.stop - start
                vals["doorway_scheduled_duration"] = max(
                    int(delta.total_seconds() / 60), 15
                )
            if activity:
                activity.with_context(
                    **{
                        SKIP_CALENDAR_SYNC_CTX: True,
                        "calendar_event_meeting_update": True,
                    }
                ).write(vals)
            else:
                todo = self.env.ref(
                    "mail.mail_activity_data_todo", raise_if_not_found=False
                )
                create_vals = {
                    **vals,
                    "res_model_id": self.env["ir.model"].sudo()._get(record._name).id,
                    "res_id": record.id,
                    "calendar_event_id": event.id,
                }
                if todo:
                    create_vals["activity_type_id"] = todo.id
                activity = Activity.create(create_vals)
            # Fiche CQ / lead : « RDV pris le » en heure du Canada (conversation client).
            if post_note and hasattr(record, "message_post"):
                event._doorway_post_rdv_pris_note(record)

    def _doorway_backfill_missing_activities(self):
        """RDV déjà liés à une fiche, sans activité."""
        domain = [
            ("res_id", "!=", False),
            ("res_model", "in", [m for m in DOORWAY_SYNC_MODELS if m in self.env]),
            ("activity_ids", "=", False),
        ]
        events = self.search(domain)
        if "coins.quebec.partenariat" in self.env:
            model = self.env["ir.model"].sudo()._get("coins.quebec.partenariat")
            parts = self.env["coins.quebec.partenariat"].sudo().search(
                [("cq_rdv_event_id", "!=", False)]
            )
            for part in parts:
                ev = part.cq_rdv_event_id
                if not ev:
                    continue
                if model and not ev.res_model_id:
                    ev.with_context(**{SKIP_ACTIVITY_SYNC_CTX: True}).write(
                        {"res_model_id": model.id, "res_id": part.id}
                    )
                events |= ev
        if events:
            events._doorway_ensure_activity_from_event(post_note=False)
        return len(events)

    def _doorway_is_booking_event(self):
        """RDV pris (wizard / IntelliX / réunion), pas activité Call / rappel."""
        self.ensure_one()
        if self.env.context.get(SKIP_ACTIVITY_SYNC_CTX):
            return False
        name = (self.name or "").strip().lower()
        if not name:
            return False
        skip = (
            "[call]",
            "[to-do]",
            "[relance",
            "rappel",
            "import —",
            "import -",
        )
        if any(marker in name for marker in skip):
            return False
        if name.startswith("[meeting]") and "rdv " not in name:
            return False
        if name.startswith("rdv ") or "rdv " in name:
            return True
        if self.opportunity_id and "intellix" in name:
            return True
        return False

    def _doorway_rdv_stage_for_lead(self, lead):
        """Colonne RDV pris / booké / En RDV / planifié du pipeline de la fiche."""
        if not lead or not lead.team_id:
            return self.env["crm.stage"].browse()
        Stage = self.env["crm.stage"].sudo()
        if "team_ids" in Stage._fields:
            stages = Stage.search(
                [("team_ids", "in", [lead.team_id.id])], order="sequence, id"
            )
        else:
            stages = Stage.search([], order="sequence, id")
        ranked = []
        for stage in stages:
            label = (stage.name or "").strip().lower()
            if label in ("rdv pris", "rdv booké", "rdv booke"):
                ranked.append((0, stage))
            elif label == "en rdv":
                ranked.append((1, stage))
            elif label in ("rdv planifié", "rdv planifie"):
                ranked.append((2, stage))
        if not ranked:
            return Stage.browse()
        ranked.sort(key=lambda item: item[0])
        return ranked[0][1]

    def _doorway_move_lead_to_rdv_stage(self):
        """crm.lead → colonne RDV du pipeline (sans reculer une fiche plus avancée)."""
        if self.env.context.get(SKIP_ACTIVITY_SYNC_CTX):
            return
        for event in self:
            if not event._doorway_is_booking_event():
                continue
            record = event._doorway_linked_record()
            if not record or record._name != "crm.lead":
                continue
            lead = record
            if lead.stage_id and lead.stage_id.is_won:
                continue
            if getattr(lead, "probability", None) == 0:
                continue
            stage = event._doorway_rdv_stage_for_lead(lead)
            if not stage or lead.stage_id == stage:
                continue
            if lead.stage_id and lead.stage_id.sequence > stage.sequence:
                continue
            lead.sudo().write({"stage_id": stage.id})

    def _doorway_is_martin_host(self):
        self.ensure_one()
        login = (self.user_id.login or "").strip().lower()
        return login == DOORWAY_MARTIN_LOGIN

    def _doorway_stamp_canada_tz(self):
        """ICS / invitation : fuseau Canada pour les RDV Martin (évite 4 h au lieu de 9 h).

        Odoo 19 : event_tz n'est pas stocké (compute récurrence). Un write
        après create lève « Unable to save the recurrence with This Event ».
        """
        field = self._fields.get("event_tz")
        if not field or not field.store:
            return
        to_stamp = self.filtered(
            lambda e: e._doorway_is_martin_host() or e._doorway_is_booking_event()
        )
        if to_stamp:
            to_stamp.with_context(**{SKIP_ACTIVITY_SYNC_CTX: True}).write(
                {"event_tz": DOORWAY_CANADA_TZ}
            )

    def _doorway_post_rdv_pris_note(self, record=None):
        """Chatter de la fiche : quand le RDV a été pris + créneau, heure du Canada."""
        self.ensure_one()
        record = record or self._doorway_linked_record()
        if not record or not hasattr(record, "message_post"):
            return
        booked = doorway_format_canada(self.create_date)
        slot = doorway_format_canada(self.start)
        booker = self.create_uid.name or ""
        extra = html2plaintext(self.description or "").strip()
        extra_html = (
            "<p>%s</p>" % escape(extra[:500]) if extra else ""
        )
        body = Markup(
            "<p><strong>RDV pris le %s</strong>%s.</p>"
            "<p>Créneau avec le client : <strong>%s</strong>.</p>%s"
            % (
                escape(booked),
                (" par %s" % escape(booker)) if booker else "",
                escape(slot),
                extra_html,
            )
        )
        record.sudo().message_post(body=body, subtype_xmlid="mail.mt_note")

    @api.model_create_multi
    def create(self, vals_list):
        Users = self.env["res.users"].sudo()
        martin = Users.search([("login", "=", DOORWAY_MARTIN_LOGIN)], limit=1)
        for vals in vals_list:
            user = Users.browse(vals.get("user_id") or 0)
            name = (vals.get("name") or "").lower()
            if (martin and user.id == martin.id) or name.startswith("rdv "):
                vals.setdefault("event_tz", DOORWAY_CANADA_TZ)
        events = super().create(vals_list)
        events._doorway_stamp_canada_tz()
        events._doorway_ensure_activity_from_event(post_note=True)
        events._doorway_move_lead_to_rdv_stage()
        return events

    def write(self, vals):
        if self.env.context.get(SKIP_ACTIVITY_SYNC_CTX) or self.env.context.get(
            "mail_activity_meeting_update"
        ):
            return super().write(vals)
        desc_changed = "description" in vals
        res = super().write(vals)
        touched = {
            "name",
            "description",
            "start",
            "stop",
            "user_id",
            "res_id",
            "res_model_id",
            "opportunity_id",
        }.intersection(vals.keys())
        if touched:
            self._doorway_ensure_activity_from_event(post_note=desc_changed)
            self._doorway_move_lead_to_rdv_stage()
        return res

    def _doorway_clean_note_text(self, body):
        """HTML chatter → texte lisible (déséchappe &lt;p&gt; des anciens miroirs)."""
        text = html2plaintext(body or "")
        for _ in range(3):
            if "&lt;" not in text and "&amp;" not in text:
                break
            text = unescape(text)
        text = unescape(text).replace("\xa0", " ").strip()
        return text

    def _doorway_should_mirror_note(self, body):
        text = self._doorway_clean_note_text(body)
        if not text:
            return False
        low = text.lower()
        if low.startswith("note de ") and "(rdv)" in low:
            return False
        if low.startswith("note calendrier"):
            return False
        if low.startswith("rdv pris le"):
            return False
        if "vous a invité" in low or "vous a invite" in low:
            return False
        if low.startswith("invitation") or "bonjour " in low[:40] and "réunion" in low:
            return False
        return True

    def _doorway_mirror_note_to_fiche(self, body, author_name=None):
        """Recopie un commentaire RDV en clair sur la fiche (Notes + chatter)."""
        if self.env.context.get("doorway_skip_event_note_mirror"):
            return
        author = author_name or self.env.user.name or ""
        text = self._doorway_clean_note_text(body)
        if not text:
            return
        for event in self:
            record = event._doorway_linked_record()
            if not record or not hasattr(record, "message_post"):
                continue
            if not self._doorway_should_mirror_note(text):
                continue
            rec = record.with_context(doorway_skip_event_note_mirror=True).sudo()
            rec.message_post(
                body=Markup("<p><strong>Note de %s (RDV)</strong> : %s</p>")
                % (escape(author), escape(text).replace("\n", Markup("<br/>"))),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            if record._name == "coins.quebec.partenariat":
                stamp = fields.Datetime.now().strftime("%d/%m/%Y %Hh%M")
                block = "Martin %s : %s" % (stamp, text)
                vals = {}
                if "cq_rdv_followup_note" in record._fields:
                    vals["cq_rdv_followup_note"] = text
                existing = (record.notes or "").strip()
                if text not in existing:
                    vals["notes"] = (existing + "\n\n" if existing else "") + block
                if vals:
                    rec.write(vals)

    def message_post(self, **kwargs):
        msg = super().message_post(**kwargs)
        if self.env.context.get("doorway_skip_event_note_mirror"):
            return msg
        messages = msg if hasattr(msg, "ids") else self.env["mail.message"]
        for message in messages:
            if message.message_type not in ("comment", "email"):
                continue
            author = message.author_id.name or self.env.user.name or ""
            self._doorway_mirror_note_to_fiche(message.body, author_name=author)
        return msg
