# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

DAVE_LOGIN = "dave.pichette@remax-quebec.com"
KARINE_LOGIN = "karine@agencedoorway.com"
DAVE_TZ = "America/Toronto"
HOLD_PREFIX = "[À confirmer] "


def _fmt_canada(dt):
    if not dt:
        return ""
    try:
        import pytz
    except ImportError:
        return fields.Datetime.to_string(dt)
    tz = pytz.timezone(DAVE_TZ)
    if getattr(dt, "tzinfo", None) is None:
        dt = pytz.utc.localize(dt)
    local = dt.astimezone(tz)
    return local.strftime("%d/%m/%Y %Hh%M") + " (heure du Canada)"


class CrmLeadDaveBooking(models.Model):
    _inherit = "crm.lead"

    dave_booking_event_id = fields.Many2one(
        "calendar.event",
        string="Créneau Dave",
        copy=False,
        ondelete="set null",
    )
    dave_booking_state = fields.Selection(
        [
            ("none", "Aucun"),
            ("pending", "À confirmer avant envoi"),
            ("confirmed", "Envoyé à Dave"),
            ("cancelled", "Libéré"),
        ],
        string="Statut créneau Dave",
        default="none",
        copy=False,
        index=True,
    )
    dave_booking_slot_display = fields.Char(
        compute="_compute_dave_booking_slot_display",
        string="Horaire proposé",
    )

    @api.depends("dave_booking_event_id", "dave_booking_event_id.start")
    def _compute_dave_booking_slot_display(self):
        for lead in self:
            ev = lead.dave_booking_event_id
            lead.dave_booking_slot_display = (
                _fmt_canada(ev.start) if ev and ev.start else ""
            )

    def _dave_pichette_user(self):
        Users = self.env["res.users"].sudo()
        user = Users.search([("login", "=", DAVE_LOGIN)], limit=1)
        if not user:
            user = Users.search([("name", "ilike", "Dave Pichette")], limit=1)
        if user and (user.tz or "") != DAVE_TZ:
            user.write({"tz": DAVE_TZ})
        return user

    def _dave_confirm_user(self):
        return self.env["res.users"].sudo().search(
            [("login", "=", KARINE_LOGIN)], limit=1
        )

    def _dave_contact_block(self):
        self.ensure_one()
        contact = (self.contact_name or self.partner_name or "").strip()
        lines = []
        if contact:
            lines.append("Contact : %s" % contact)
        phones = []
        for raw in (self.phone, getattr(self, "mobile", None)):
            num = (raw or "").strip()
            if num and num not in phones:
                phones.append(num)
        if phones:
            lines.append("Téléphones : %s" % " ; ".join(phones))
        addr = ", ".join(
            x
            for x in [
                (self.street or "").strip(),
                (getattr(self, "street2", None) or "").strip(),
                (self.city or "").strip(),
                (self.zip or "").strip(),
            ]
            if x
        )
        if addr:
            lines.append("Adresse : %s" % addr)
        if (self.email_from or "").strip():
            lines.append("Email : %s" % self.email_from.strip())
        return lines

    def _dave_event_busy(self, dave, start, minutes=30, exclude_event=None):
        Event = self.env["calendar.event"].sudo()
        domain = [
            ("user_id", "=", dave.id),
            ("active", "=", True),
            ("start", "<", start + timedelta(minutes=minutes)),
            ("stop", ">", start),
        ]
        if exclude_event:
            domain.append(("id", "!=", exclude_event.id))
        return bool(Event.search_count(domain))

    def _dave_next_free_slot(self, after=None):
        dave = self._dave_pichette_user()
        if not dave:
            return False
        try:
            import pytz
        except ImportError:
            pytz = None
        tz = pytz.timezone(DAVE_TZ) if pytz else None
        now = fields.Datetime.now()
        if after and after > now:
            now = after
        if tz:
            local_now = pytz.utc.localize(now).astimezone(tz)
            day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for _ in range(30):
            day = day + timedelta(days=1)
            for hour in range(9, 20):
                for minute in (0, 30):
                    if tz:
                        slot_local = day.replace(hour=hour, minute=minute)
                        if slot_local <= local_now:
                            continue
                        slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    else:
                        slot_utc = day.replace(hour=hour, minute=minute)
                        if slot_utc <= now:
                            continue
                    if not self._dave_event_busy(dave, slot_utc):
                        return slot_utc
        return False

    def _dave_ensure_contact_partner(self):
        self.ensure_one()
        if self.partner_id:
            partner = self.partner_id
            upd = {}
            if self.phone and not partner.phone:
                upd["phone"] = self.phone
            if self.email_from and not partner.email:
                upd["email"] = self.email_from
            if self.street and not partner.street:
                upd["street"] = self.street
            if self.city and not partner.city:
                upd["city"] = self.city
            if upd:
                partner.sudo().write(upd)
            return partner
        name = (self.contact_name or self.partner_name or self.name or "Contact").strip()
        partner = self.env["res.partner"].sudo().create(
            {
                "name": name,
                "phone": self.phone or False,
                "email": (self.email_from or "").strip() or False,
                "street": self.street or False,
                "city": self.city or False,
                "zip": self.zip or False,
                "is_company": False,
            }
        )
        self.sudo().write({"partner_id": partner.id})
        return partner

    def _dave_hold_slot_at(self, start, notify_todo=True):
        """Réserve le créneau sur l’agenda Dave sans lui envoyer l’invitation."""
        self.ensure_one()
        dave = self._dave_pichette_user()
        if not dave:
            return {"ok": False, "reason": "no_dave"}
        if not start:
            return {"ok": False, "reason": "no_slot"}
        if self._dave_event_busy(dave, start):
            return {"ok": False, "reason": "busy"}
        contact = (self.contact_name or self.partner_name or self.name or "").strip()
        where = (self.street or self.city or "").strip()
        title = "Évaluation %s" % (contact or self.name)
        if where:
            title = "%s — %s" % (title, where)
        desc_bits = [
            html_escape("Évaluation marchande — créneau proposé, pas encore envoyé à Dave."),
            html_escape("Confirmer sur la fiche avant l’invitation calendrier."),
        ]
        for line in self._dave_contact_block():
            desc_bits.append(html_escape(line))
        model = self.env["ir.model"].sudo()._get("crm.lead")
        vals = {
            "name": HOLD_PREFIX + title,
            "start": start,
            "stop": start + timedelta(minutes=30),
            "user_id": dave.id,
            "description": "<br/>".join(desc_bits),
            "res_id": self.id,
        }
        if model:
            vals["res_model_id"] = model.id
        event = (
            self.env["calendar.event"]
            .sudo()
            .with_context(
                tz="UTC",
                no_mail_to_attendees=True,
                doorway_skip_activity_sync=True,
                mail_activity_meeting_update=True,
            )
            .create(vals)
        )
        old = self.dave_booking_event_id
        self.sudo().write(
            {
                "dave_booking_event_id": event.id,
                "dave_booking_state": "pending",
            }
        )
        if old and old.exists() and old.id != event.id:
            old.with_context(
                no_mail_to_attendees=True,
                doorway_skip_activity_sync=True,
            ).unlink()
        if notify_todo:
            self._dave_schedule_confirm_activity(start)
        if hasattr(self, "message_post"):
            self.sudo().message_post(
                body="Créneau Dave proposé : <strong>%s</strong>. À confirmer avant envoi."
                % html_escape(_fmt_canada(start)),
                subtype_xmlid="mail.mt_note",
            )
        return {"ok": True, "event_id": event.id, "start": fields.Datetime.to_string(start)}

    def _dave_schedule_confirm_activity(self, start):
        self.ensure_one()
        karine = self._dave_confirm_user()
        user = karine or self.user_id
        if not user:
            return
        summary = "Confirmer le créneau Dave Pichette (%s) avant envoi" % _fmt_canada(
            start
        )
        existing = self.activity_ids.filtered(
            lambda a: a.summary and a.summary.startswith("Confirmer le créneau Dave")
        )
        if existing:
            existing.write({"summary": summary, "user_id": user.id})
            return
        self.sudo().activity_schedule(
            "mail.mail_activity_data_todo",
            summary=summary,
            note="Le créneau est réservé sur l’agenda de Dave. Confirmer pour lui envoyer l’invitation.",
            user_id=user.id,
        )

    def _dave_auto_hold_slot(self):
        result = {"ok": False, "reason": "empty"}
        for lead in self:
            if lead.dave_booking_state == "confirmed" and lead.dave_booking_event_id:
                result = {"ok": True, "event_id": lead.dave_booking_event_id.id, "already": True}
                continue
            start = lead._dave_next_free_slot()
            result = lead._dave_hold_slot_at(start) if start else {"ok": False, "reason": "no_slot"}
            if not start and hasattr(lead, "message_post"):
                lead.sudo().message_post(
                    body="Aucun créneau Dave libre sur 30 jours.",
                    subtype_xmlid="mail.mt_note",
                )
        return result

    def action_dave_auto_hold(self):
        self.ensure_one()
        info = self._dave_auto_hold_slot()
        if not info.get("ok"):
            raise UserError("Impossible de réserver un créneau Dave (%s)." % info.get("reason"))
        return True

    def action_dave_cancel_hold(self):
        self.ensure_one()
        ev = self.dave_booking_event_id
        if ev:
            ev.with_context(
                no_mail_to_attendees=True,
                doorway_skip_activity_sync=True,
            ).unlink()
        self.sudo().write(
            {
                "dave_booking_event_id": False,
                "dave_booking_state": "cancelled",
            }
        )
        todo = self.activity_ids.filtered(
            lambda a: a.summary and a.summary.startswith("Confirmer le créneau Dave")
        )
        todo.unlink()
        if hasattr(self, "message_post"):
            self.sudo().message_post(
                body="Créneau Dave libéré — rien n’a été envoyé.",
                subtype_xmlid="mail.mt_note",
            )
        return True

    def action_dave_confirm_send(self):
        """Passe le créneau à Dave : invitation calendrier + assignation fiche."""
        return self._dave_confirm_send(send_mail=True)

    def _dave_confirm_send(self, send_mail=True):
        self.ensure_one()
        dave = self._dave_pichette_user()
        if not dave:
            raise UserError("Compte Dave Pichette introuvable.")
        ev = self.dave_booking_event_id
        if not ev or not ev.exists():
            info = self._dave_auto_hold_slot()
            ev = self.dave_booking_event_id
            if not ev:
                raise UserError("Aucun créneau à confirmer (%s)." % (info or {}).get("reason"))
        contact = self._dave_ensure_contact_partner()
        attendees = [dave.partner_id.id]
        if contact and contact.id != dave.partner_id.id:
            attendees.append(contact.id)
        title = (ev.name or "").replace(HOLD_PREFIX, "", 1)
        desc_bits = [
            html_escape("Évaluation marchande — confirmée, invitation envoyée à Dave Pichette."),
        ]
        for line in self._dave_contact_block():
            desc_bits.append(html_escape(line))
        ctx = {
            "doorway_skip_activity_sync": True,
            "mail_activity_meeting_update": True,
        }
        if not send_mail:
            ctx["no_mail_to_attendees"] = True
        ev.sudo().with_context(**ctx).write(
            {
                "name": title,
                "description": "<br/>".join(desc_bits),
                "partner_ids": [(6, 0, attendees)],
                "user_id": dave.id,
            }
        )
        if send_mail:
            to_notify = ev.sudo().attendee_ids.filtered(
                lambda a: a.partner_id == dave.partner_id
            )
            if to_notify:
                to_notify.with_context(no_mail_to_attendees=False)._send_invitation_emails()
        self.sudo().write(
            {
                "user_id": dave.id,
                "dave_booking_state": "confirmed",
            }
        )
        todo = self.activity_ids.filtered(
            lambda a: a.summary and a.summary.startswith("Confirmer le créneau Dave")
        )
        if hasattr(todo, "action_feedback"):
            todo.action_feedback(feedback="Confirmé — invitation envoyée à Dave.")
        else:
            todo.unlink()
        if hasattr(self, "message_post"):
            self.sudo().message_post(
                body="Créneau <strong>%s</strong> confirmé et envoyé à Dave Pichette."
                % html_escape(self.dave_booking_slot_display or ""),
                subtype_xmlid="mail.mt_note",
            )
        return True


class RenovationMetaImmoDaveBooking(models.AbstractModel):
    _inherit = "renovation.meta.immo.webhook"

    @api.model
    def create_lead_from_meta(self, data):
        result, status = super().create_lead_from_meta(data)
        if status == 200 and result.get("status") == "success" and result.get("lead_id"):
            lead = self.env["crm.lead"].sudo().browse(result["lead_id"])
            if lead.exists():
                result["dave_booking"] = lead._dave_auto_hold_slot()
        return result, status


class RenovationWebsiteLeadDaveBooking(models.AbstractModel):
    _inherit = "renovation.website.lead.webhook"

    @api.model
    def _dave_payload_is_pichette(self, data, pipeline_key):
        form_type = str(data.get("form_type") or "").strip().lower()
        if form_type in (
            "geo_evaluation_dave",
            "pichette",
            "evaluation_dave",
            "evaluation_marchande",
        ):
            return True
        site = (
            str(data.get("site_source") or data.get("site") or "")
            .lower()
            .replace("www.", "")
        )
        if "maisonrecherchee.com" in site:
            return True
        if str(data.get("pipeline") or "").strip().lower() == "immobilier":
            return True
        return pipeline_key == "immobilier"

    @api.model
    def create_lead_from_website_payload(self, pipeline_key, data):
        result, status = super().create_lead_from_website_payload(pipeline_key, data)
        if status != 200 or result.get("status") != "success":
            return result, status
        if not self._dave_payload_is_pichette(data, pipeline_key):
            return result, status
        lead = self.env["crm.lead"].sudo().browse(result.get("lead_id"))
        if lead.exists():
            result["dave_booking"] = lead._dave_auto_hold_slot()
        return result, status
