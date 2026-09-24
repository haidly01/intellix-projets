# -*- coding: utf-8 -*-
"""WhatsApp / n8n pour événements Coins Marocain — réutilise le webhook détente."""
import logging
from datetime import datetime, timedelta, time

import requests

from odoo import _, fields
from odoo.addons.coins_marocain.services.yasmine_service import YasmineService

_logger = logging.getLogger(__name__)


class CoinsEvenementService:
    def __init__(self, env):
        self.env = env
        self.icp = env["ir.config_parameter"].sudo()
        self.wa = YasmineService(env)

    def _n8n_webhook_url(self):
        return (
            self.icp.get_param("coins_marocain.n8n_confirm_webhook_url")
            or "http://127.0.0.1:5678/webhook/coins-detente-confirm"
        )

    def _post_n8n(self, payload):
        url = self._n8n_webhook_url()
        try:
            requests.post(url, json=payload, timeout=15)
        except Exception as exc:
            _logger.warning("coins evenement n8n fail: %s", exc)

    def _format_dt(self, dt):
        if not dt:
            return "—"
        return fields.Datetime.to_string(dt)[:16].replace("T", " ")

    def _place(self, ev):
        return (
            (ev.property_id.name if ev.property_id else None)
            or (ev.partner_activity_id.name if ev.partner_activity_id else None)
            or "Marrakech"
        )

    def build_invitation_message(self, invite):
        ev = invite.evenement_id
        name = (invite.name or "invité(e)").split()[0]
        return (
            "Bonjour %(name)s 👋\n\n"
            "Vous êtes invité(e) à %(event)s\n"
            "📅 %(when)s\n"
            "📍 %(place)s\n\n"
            "Merci de confirmer votre présence en répondant à ce message.\n"
            "À très bientôt 🧡\n"
            "— Coins Marocain"
        ) % {
            "name": name,
            "event": ev.name,
            "when": self._format_dt(ev.date_start),
            "place": self._place(ev),
        }

    def build_j1_reminder_message(self, invite):
        ev = invite.evenement_id
        return (
            "Rappel 📅\n\n"
            "Demain : %(event)s\n"
            "🕐 %(when)s\n"
            "📍 %(place)s\n\n"
            "On a hâte de vous voir !"
        ) % {
            "event": ev.name,
            "when": self._format_dt(ev.date_start),
            "place": self._place(ev),
        }

    def send_invitation(self, invite):
        phone = (invite.phone or "").strip()
        if not phone:
            return False
        body = self.build_invitation_message(invite)
        wa_ok = False
        if hasattr(self.wa, "send_whatsapp"):
            try:
                wa_ok = bool(self.wa.send_whatsapp(phone, body))
            except Exception as exc:
                _logger.warning("coins evenement WA invite fail: %s", exc)
        self._post_n8n(
            {
                "type": "coins_evenement_invite",
                "event_ref": invite.evenement_id.reference,
                "invite_id": invite.id,
                "client_phone": phone,
                "message": body,
                "odoo_results": {"client_ok": bool(wa_ok)},
            }
        )
        return bool(wa_ok)

    def notify_j1_reminders(self):
        today = fields.Date.context_today(self.env.user)
        tomorrow = today + timedelta(days=1)
        start = fields.Datetime.to_datetime(datetime.combine(tomorrow, time.min))
        end = start + timedelta(days=1)
        events = self.env["coins.evenement"].sudo().search(
            [
                ("state", "in", ("confirmed", "deposit_received", "day_j")),
                ("date_start", ">=", start),
                ("date_start", "<", end),
            ]
        )
        sent = 0
        for ev in events:
            invites = ev.invite_ids.filtered(
                lambda i: i.rsvp_state == "confirmed"
                and i.phone
                and not i.reminder_sent
            )
            for invite in invites:
                body = self.build_j1_reminder_message(invite)
                ok = False
                if hasattr(self.wa, "send_whatsapp"):
                    try:
                        ok = bool(self.wa.send_whatsapp(invite.phone, body))
                    except Exception as exc:
                        _logger.warning("coins evenement WA j1 fail: %s", exc)
                self._post_n8n(
                    {
                        "type": "coins_evenement_j1_reminder",
                        "event_ref": ev.reference,
                        "invite_id": invite.id,
                        "client_phone": invite.phone,
                        "message": body,
                        "odoo_results": {"client_ok": bool(ok)},
                    }
                )
                if ok:
                    invite.reminder_sent = True
                    sent += 1
        return sent

    def notify_prestataire_quote_overdue(self):
        """Relance Karine/Zakaria si devis demandé > 3 jours sans réponse."""
        limit = fields.Date.context_today(self.env.user) - timedelta(days=3)
        lines = self.env["coins.evenement.prestataire"].sudo().search(
            [
                ("confirmation_state", "=", "quote_requested"),
                ("quote_requested_date", "<=", limit),
            ]
        )
        if not lines:
            return 0
        zak = (
            self.icp.get_param("coins_marocain.zakaria_whatsapp")
            or self.icp.get_param("coins_marocain.emergency_whatsapp")
            or ""
        ).lstrip("+")
        body_lines = []
        for line in lines:
            body_lines.append(
                "• %(ev)s — %(partner)s (%(cat)s) depuis %(d)s"
                % {
                    "ev": line.evenement_id.name,
                    "partner": line.display_name,
                    "cat": line.category,
                    "d": line.quote_requested_date or "?",
                }
            )
        body = (
            "Relance prestataires événement ⏰\n\n"
            + "\n".join(body_lines[:15])
            + "\n\nVoir Odoo → Événements"
        )
        sent = 0
        if zak and hasattr(self.wa, "send_whatsapp"):
            try:
                if self.wa.send_whatsapp(zak, body):
                    sent += 1
            except Exception as exc:
                _logger.warning("coins evenement WA relance fail: %s", exc)
        karine = self.icp.get_param("coins_marocain.karine_email")
        if karine:
            try:
                self.env["mail.mail"].sudo().create(
                    {
                        "subject": _("Relance devis prestataires événement"),
                        "body_html": "<pre>%s</pre>" % body,
                        "email_to": karine,
                    }
                ).send()
                sent += 1
            except Exception:
                pass
        return sent
