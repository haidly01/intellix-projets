# -*- coding: utf-8 -*-
"""Note vocale CRM : dicter une note et créer des activités."""
import logging
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}

ACTIVITY_TRIGGERS = re.compile(
    r"\b("
    r"activit[eé]s?|rappeler|relancer|appeler|todo|"
    r"t[aâ]che|\u00e0\s+faire|a\s+faire|"
    r"rendez[-\s]?vous|\brdv\b|planifier|suivi"
    r")\b",
    re.IGNORECASE,
)

TYPE_XMLIDS = {
    "call": "mail.mail_activity_data_call",
    "email": "mail.mail_activity_data_email",
    "meeting": "mail.mail_activity_data_meeting",
    "todo": "mail.mail_activity_data_todo",
}


def _fold(text):
    import unicodedata

    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip().lower()


def _next_weekday(day, weekday):
    delta = (weekday - day.weekday()) % 7
    if delta == 0:
        delta = 7
    return day + timedelta(days=delta)


class DoorwayCrmLeadVoiceNote(models.Model):
    _inherit = "crm.lead"

    def _voice_user_now(self):
        tz_name = self.env.user.tz or "America/Toronto"
        tz = pytz.timezone(tz_name)
        return datetime.now(tz), tz

    def _parse_voice_when(self, text):
        folded = _fold(text)
        now, tz = self._voice_user_now()
        day = now.date()
        hour = minute = None

        hm = re.search(r"\b(\d{1,2})\s*h(?:eures?)?\s*(\d{2})?\b", folded)
        if hm:
            hour = min(int(hm.group(1)), 23)
            minute = min(int(hm.group(2) or 0), 59)

        if re.search(r"\bapres[-\s]?demain\b", folded):
            day = day + timedelta(days=2)
        elif re.search(r"\bdemain\b", folded):
            day = day + timedelta(days=1)
        elif re.search(r"\baujourd.?hui\b", folded):
            day = now.date()
        else:
            days_m = re.search(r"\bdans\s+(\d+)\s+jours?\b", folded)
            if days_m:
                day = now.date() + timedelta(days=int(days_m.group(1)))
            else:
                for name, wd in WEEKDAYS.items():
                    if re.search(rf"\b{name}\b", folded):
                        day = _next_weekday(now.date(), wd)
                        break
            date_m = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b", folded)
            if date_m:
                d, mo = int(date_m.group(1)), int(date_m.group(2))
                y = int(date_m.group(3) or now.year)
                if y < 100:
                    y += 2000
                try:
                    day = datetime(y, mo, d).date()
                except ValueError:
                    pass

        start = None
        if hour is not None:
            local = tz.localize(datetime.combine(day, time(hour, minute or 0)))
            start = local.astimezone(pytz.UTC).replace(tzinfo=None)
        return day, start

    def _parse_voice_activity_type(self, text):
        folded = _fold(text)
        if re.search(r"\b(appel|appeler|rappeler|telephone|tel)\b", folded):
            return "call"
        if re.search(r"\b(email|e-?mail|courriel|mail)\b", folded):
            return "email"
        if re.search(r"\b(rdv|rendez[-\s]?vous|reunion|meeting|visio)\b", folded):
            return "meeting"
        return "todo"

    def _voice_activity_summary(self, text):
        folded = _fold(text)
        cleaned = folded
        cleaned = ACTIVITY_TRIGGERS.sub(" ", cleaned)
        cleaned = re.sub(
            r"\b(demain|apres[-\s]?demain|aujourd.?hui|lundi|mardi|mercredi|"
            r"jeudi|vendredi|samedi|dimanche|dans\s+\d+\s+jours?|"
            r"\d{1,2}\s*h(?:eures?)?(?:\s*\d{2})?|a\s+\d{1,2}|"
            r"creer|nouvelle|une|un|le|la|les|de|du|des)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"[^\w\s'\-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        stop = {"heure", "heures", "h", "minute", "minutes", "matin", "apres", "midi", "soir"}
        cleaned = " ".join(w for w in cleaned.split() if w not in stop)
        if not cleaned or len(cleaned) < 3:
            kind = self._parse_voice_activity_type(text)
            return {
                "call": "Rappeler",
                "email": "Envoyer un courriel",
                "meeting": "Rendez-vous",
                "todo": "Suivi",
            }[kind]
        return cleaned[:120].capitalize()

    def _voice_activity_type_record(self, kind):
        xmlid = TYPE_XMLIDS.get(kind) or TYPE_XMLIDS["todo"]
        rec = self.env.ref(xmlid, raise_if_not_found=False)
        if rec:
            return rec
        name_map = {
            "call": "Appel",
            "email": "Email",
            "meeting": "Rendez-vous",
            "todo": "À faire",
        }
        return self.env["mail.activity.type"].search(
            [("name", "ilike", name_map.get(kind, "faire"))], limit=1
        ) or self.env["mail.activity.type"].search([], limit=1)

    def _create_voice_activity(self, transcript):
        self.ensure_one()
        kind = self._parse_voice_activity_type(transcript)
        deadline, start = self._parse_voice_when(transcript)
        summary = self._voice_activity_summary(transcript)
        act_type = self._voice_activity_type_record(kind)
        model = self.env["ir.model"]._get("crm.lead")
        vals = {
            "res_model_id": model.id,
            "res_id": self.id,
            "activity_type_id": act_type.id if act_type else False,
            "summary": summary,
            "note": f"<p>{html_escape(transcript)}</p>",
            "date_deadline": deadline,
            # Assigner à la personne qui dicte, pas au user_id de la fiche
            # (souvent __system__ / admin) — sinon l'activité est invisible.
            "user_id": (
                self.env.user.id
                if self.env.user.login not in ("__system__", "admin")
                else (self.user_id.id or self.env.uid)
            ),
        }
        if start:
            vals["doorway_scheduled_start"] = start
            vals["doorway_scheduled_duration"] = 30
        return self.env["mail.activity"].create(vals)

    @api.model
    def action_voice_note(self, lead_id, transcript, source="note"):
        """Dicte une note interne et crée une activité si l'intention est là."""
        lead = self.browse(int(lead_id))
        if not lead.exists():
            return {"ok": False, "message": _("Opportunité introuvable. Enregistrez d'abord la fiche.")}
        text = (transcript or "").strip()
        if not text:
            return {"ok": False, "message": _("Rien entendu.")}

        now, _tz = lead._voice_user_now()
        stamp = now.strftime("%Y-%m-%d %H:%M")
        block = f"<p><em>[{html_escape(stamp)} vocal]</em> {html_escape(text)}</p>"
        current = lead.description or ""
        lead.write({"description": current + block})
        # Chatter = ce que Zakaria / l'équipe appelle « notes du CRM ».
        # description (onglet interne / widget collaboratif) ne s'y affiche pas.
        try:
            lead.message_post(
                body=block,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        except Exception:
            _logger.exception("voice note chatter post failed lead=%s", lead.id)
        for fname in ("coins_relance_notes", "coins_notes_visite"):
            if fname in lead._fields:
                prev = lead[fname] or ""
                sep = "\n" if prev else ""
                lead.write({fname: f"{prev}{sep}[{stamp} vocal] {text}"})

        created = []
        if ACTIVITY_TRIGGERS.search(_fold(text)) or source == "activity":
            try:
                act = lead._create_voice_activity(text)
                created.append(
                    {
                        "id": act.id,
                        "summary": act.summary,
                        "date": str(act.date_deadline),
                        "type": act.activity_type_id.name or "",
                        "when": str(act.doorway_scheduled_start or act.date_deadline),
                    }
                )
            except Exception as exc:
                _logger.exception("voice activity create failed")
                return {
                    "ok": True,
                    "note_appended": True,
                    "activities": [],
                    "message": _("Note enregistrée. Activité non créée : %s") % exc,
                    "reload": True,
                }

        if created:
            act = created[0]
            msg = _("Note + activité : %(type)s — %(summary)s (%(when)s)") % {
                "type": act["type"],
                "summary": act["summary"],
                "when": act["when"],
            }
        else:
            msg = _("Note vocale enregistrée.")
        return {
            "ok": True,
            "note_appended": True,
            "activities": created,
            "message": msg,
            "reload": True,
        }

    def action_felix_handoff_martin(self, disponibilite="", travaux="", budget=""):
        """Félix a qualifié : Martin attribue aux partenaires (ville + dispos + travaux + budget)."""
        martin = self.env["res.users"].sudo().search(
            [("login", "=", "martin@agencedoorway.com")], limit=1
        )
        if not martin:
            return {"ok": False, "message": _("Utilisateur Martin introuvable.")}
        tag_q = self.env["crm.tag"].sudo().search([("name", "=", "Qualifié Félix")], limit=1)
        if not tag_q:
            tag_q = self.env["crm.tag"].sudo().create({"name": "Qualifié Félix"})
        tag_old = self.env["crm.tag"].sudo().search([("name", "=", "À qualifier Félix")], limit=1)
        for lead in self:
            city = (lead.city or "").strip()
            dispo = (disponibilite or "").strip()
            works = (travaux or "").strip()
            budg = (budget or "").strip()
            packet = (
                "<p><b>Félix → Martin — à attribuer partenaire</b></p>"
                f"<ul><li><b>Ville</b> : {html_escape(city or 'MANQUANTE')}</li>"
                f"<li><b>Disponibilités client</b> : {html_escape(dispo or 'à préciser')}</li>"
                f"<li><b>Travaux</b> : {html_escape(works or 'voir formulaire')}</li>"
                f"<li><b>Budget</b> : {html_escape(budg or 'non communiqué')}</li>"
                f"<li><b>Tél</b> : {html_escape(lead.phone or '')}</li>"
                f"<li><b>Contact</b> : {html_escape(lead.contact_name or lead.partner_name or '')}</li></ul>"
            )
            vals = {"user_id": martin.id}
            tag_cmds = []
            if tag_q:
                tag_cmds.append((4, tag_q.id))
            if tag_old:
                tag_cmds.append((3, tag_old.id))
            if tag_cmds:
                vals["tag_ids"] = tag_cmds
            lead.write(vals)
            lead.message_post(body=packet, message_type="comment", subtype_xmlid="mail.mt_note")
            model = self.env["ir.model"]._get("crm.lead")
            act_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
            self.env["mail.activity"].create({
                "res_model_id": model.id,
                "res_id": lead.id,
                "activity_type_id": act_type.id if act_type else False,
                "user_id": martin.id,
                "summary": f"Attribuer partenaires — {city or 'ville manquante'}",
                "note": packet,
            })
        return {"ok": True, "martin_id": martin.id, "leads": self.ids}
