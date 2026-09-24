# -*- coding: utf-8 -*-
"""Le Créateur d'Expérience — un seul agent (bien-être + messages voyageurs).

Réponses auto uniquement sur des faits lus dans Odoo.
Hors script / prix / plainte / privatisation → Anna, jamais d'improvisation.
"""

import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

CHANNELS = [
    ("booking", "Booking"),
    ("airbnb", "Airbnb"),
    ("whatsapp", "WhatsApp"),
    ("email", "E-mail"),
    ("website", "Site direct"),
    ("messenger", "Messenger"),
    ("other", "Autre"),
]

ESCALATE_PRICE = re.compile(
    r"\b(rabais|remise|r[ée]duc|moins\s+cher|n[ée]goci|discount|cheaper|"
    r"deal|promo|best\s+price|prix\s+ami)\b",
    re.I,
)
ESCALATE_COMPLAINT = re.compile(
    r"\b(plainte|d[ée][cç]u|insatisf|scandale|inacceptable|horreur|"
    r"complaint|disappointed|refund|remboursement|arnaque|sale|"
    r"inadmissible|col[eè]re)\b",
    re.I,
)
ESCALATE_PRIVATISATION = re.compile(
    r"\b(privatis|riad\s+entier|maison\s+enti[eè]re|buyout|"
    r"entire\s+(riad|house|property)|exclusive\s+hire)\b",
    re.I,
)
# Même logique hot-handoff Yasmine (humain / urgence) — pas une nouvelle grille.
HUMAN_HANDOFF_RE = re.compile(
    r"\b(humain|agent|conseiller|parler\s+[àa]\s+quelqu|"
    r"appeler|urgence|urgent|asap|immédiat|au\s+secours|"
    r"human|speak\s+to\s+(someone|a\s+person)|call\s+me)\b",
    re.I,
)
AUTO_AVAIL = re.compile(
    r"\b(dispo|disponib|available|vacan|libre|occup[ée]|chambre)\b",
    re.I,
)
AUTO_RATE = re.compile(
    r"\b(prix|tarif|rate|combien|co[uû]t|nightly|par\s+nuit)\b",
    re.I,
)
AUTO_PRACTICAL = re.compile(
    r"\b(kasbah|quartier|check[\s-]?in|check[\s-]?out|arriv[ée]e|"
    r"comment\s+(venir|arriver)|adresse|m[ée]dina|wifi|acc[eè]s)\b",
    re.I,
)
AUTO_WELLNESS = re.compile(
    r"\b(massage|hammam|soin|beaut[ée]|brushing|ongle|esth[ée]tique|"
    r"rendez[\s-]?vous|rdv|spa|bien[\s-]?[êe]tre|manucure|p[ée]dicure)\b",
    re.I,
)
AUTO_RESTAURANT = re.compile(
    r"\b(restaurant|terrasse|carte|menu|d[iî]ner|dejeuner|déjeuner|"
    r"demi[\s-]?pension|tajine|couscous|plat|entr[ée]e|dessert|"
    r"th[ée]\s+[àa]\s+la\s+menthe|boisson)\b",
    re.I,
)


def _norm(text):
    return (text or "").strip()


class IntellixRiadExperienceThread(models.Model):
    _name = "intellix.riad.experience.thread"
    _description = "Tour Créateur d'Expérience"
    _order = "inbound_at desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(compute="_compute_name", store=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    channel = fields.Selection(CHANNELS, required=True, default="other")
    inbox_id = fields.Many2one("doorway.social.inbox", ondelete="set null")
    reservation_id = fields.Many2one("coins.reservation", ondelete="set null")
    wellness_slot_id = fields.Many2one("intellix.riad.wellness.slot", ondelete="set null")
    guest_name = fields.Char()
    inbound_text = fields.Text()
    reply_text = fields.Text()
    intent = fields.Selection(
        [
            ("availability", "Disponibilité chambres"),
            ("rate", "Tarifs"),
            ("practical", "Infos pratiques"),
            ("wellness", "Bien-être / beauté"),
            ("restaurant", "Restaurant / terrasse"),
            ("escalate_price", "Escalade — prix"),
            ("escalate_complaint", "Escalade — plainte"),
            ("escalate_privatisation", "Escalade — privatisation"),
            ("escalate_human", "Escalade — humain / urgence"),
            ("escalate_oos", "Escalade — hors script"),
        ],
        required=True,
    )
    decision = fields.Selection(
        [("auto", "Réponse auto"), ("escalate", "Anna (humain)")],
        required=True,
        index=True,
    )
    inbound_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    replied_at = fields.Datetime()
    response_seconds = fields.Integer(compute="_compute_response_seconds", store=True)
    state = fields.Selection(
        [("open", "Ouvert"), ("replied", "Répondu"), ("closed", "Clos")],
        default="open",
        tracking=True,
    )

    @api.depends("channel", "intent", "guest_name", "inbound_at")
    def _compute_name(self):
        intents = dict(self._fields["intent"].selection)
        for rec in self:
            rec.name = "%s · %s · %s" % (
                dict(CHANNELS).get(rec.channel) or rec.channel,
                intents.get(rec.intent) or rec.intent,
                rec.guest_name or (rec.inbound_at and rec.inbound_at.strftime("%d/%m %Hh%M") or ""),
            )

    @api.depends("inbound_at", "replied_at")
    def _compute_response_seconds(self):
        for rec in self:
            if rec.inbound_at and rec.replied_at:
                rec.response_seconds = max(
                    int((rec.replied_at - rec.inbound_at).total_seconds()), 0
                )
            else:
                rec.response_seconds = 0

    def action_mark_replied(self, reply_text=None):
        now = fields.Datetime.now()
        for rec in self:
            vals = {"replied_at": now, "state": "replied"}
            if reply_text:
                vals["reply_text"] = reply_text
            rec.write(vals)
        return True

    @api.model
    def average_response_seconds(self, establishment, days=30):
        if not establishment:
            return None
        since = fields.Datetime.now() - timedelta(days=days)
        rows = self.search(
            [
                ("establishment_id", "=", establishment.id),
                ("replied_at", "!=", False),
                ("inbound_at", ">=", since),
                ("response_seconds", ">", 0),
            ]
        )
        if not rows:
            return None
        return int(sum(rows.mapped("response_seconds")) / float(len(rows)))


class IntellixRiadExperienceAgent(models.AbstractModel):
    _name = "intellix.riad.experience.agent"
    _description = "Créateur d'Expérience (un seul agent)"

    def _establishment_for_inbox(self, inbox):
        Estab = self.env["intellix.riad.establishment"]
        if inbox and inbox.account_id:
            found = Estab.search(
                [("social_account_id", "=", inbox.account_id.id)], limit=1
            )
            if found:
                return found
        # Pas de fallback « premier agent actif » — isolation inter-lieux.
        return Estab.browse()

    def should_handle_inbox(self, inbox):
        estab = self._establishment_for_inbox(inbox)
        return bool(estab and estab.experience_agent_enabled)

    def classify(self, text):
        raw = _norm(text)
        if not raw:
            return "escalate_oos"
        if HUMAN_HANDOFF_RE.search(raw):
            return "escalate_human"
        if ESCALATE_PRIVATISATION.search(raw):
            return "escalate_privatisation"
        if ESCALATE_COMPLAINT.search(raw):
            return "escalate_complaint"
        if ESCALATE_PRICE.search(raw):
            return "escalate_price"
        wellness = bool(AUTO_WELLNESS.search(raw))
        restaurant = bool(AUTO_RESTAURANT.search(raw))
        practical = bool(AUTO_PRACTICAL.search(raw))
        rate = bool(AUTO_RATE.search(raw))
        avail = bool(AUTO_AVAIL.search(raw))
        if wellness:
            return "wellness"
        if restaurant:
            return "restaurant"
        if practical and not rate:
            return "practical"
        if rate:
            return "rate"
        if avail:
            return "availability"
        return "escalate_oos"

    def handle_inbox_message(self, inbox, text):
        estab = self._establishment_for_inbox(inbox)
        if not estab:
            return False
        channel = inbox.inbox_source if inbox.inbox_source in dict(CHANNELS) else "other"
        if inbox.inbox_source == "whatsapp":
            channel = "whatsapp"
        return self.handle_message(
            estab,
            text,
            channel=channel,
            inbox=inbox,
            guest_name=inbox.external_name or "",
        )

    def handle_message(
        self,
        estab,
        text,
        channel="other",
        inbox=None,
        guest_name="",
        reservation=None,
    ):
        intent = self.classify(text)
        escalate = intent.startswith("escalate_")
        thread = self.env["intellix.riad.experience.thread"].create(
            {
                "establishment_id": estab.id,
                "channel": channel if channel in dict(CHANNELS) else "other",
                "inbox_id": inbox.id if inbox else False,
                "reservation_id": reservation.id if reservation else False,
                "guest_name": guest_name or (inbox.external_name if inbox else ""),
                "inbound_text": (text or "")[:4000],
                "intent": intent,
                "decision": "escalate" if escalate else "auto",
                "inbound_at": fields.Datetime.now(),
                "state": "open",
            }
        )
        if escalate:
            self._escalate_to_anna(thread, estab, inbox)
            return False
        reply = self._draft_reply(estab, intent, text)
        if not reply:
            thread.write({"intent": "escalate_oos", "decision": "escalate"})
            self._escalate_to_anna(thread, estab, inbox)
            return False
        reply = self._maybe_polish(estab, reply)
        thread.action_mark_replied(reply)
        return reply

    def _escalate_to_anna(self, thread, estab, inbox):
        summary = {
            "escalate_price": _("Négociation / rabais — à traiter par Anna"),
            "escalate_complaint": _("Plainte — à traiter par Anna"),
            "escalate_privatisation": _("Demande de privatisation — à traiter par Anna"),
            "escalate_human": _(
                "Hot-handoff (mot-clé humain/urgence) — même logique Yasmine"
            ),
            "escalate_oos": _("Hors script — Anna doit répondre"),
        }.get(thread.intent, _("Escalade Créateur d'Expérience"))
        if inbox:
            inbox.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=thread.inbound_text or "",
            )
        else:
            estab.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=thread.inbound_text or "",
            )
        self._notify_n8n(estab, thread)

    def _notify_n8n(self, estab, thread):
        url = (estab.experience_n8n_webhook or "").strip()
        if not url:
            return
        try:
            import requests

            requests.post(
                url,
                json={
                    "event": "experience_escalate",
                    "establishment_id": estab.id,
                    "thread_id": thread.id,
                    "intent": thread.intent,
                    "channel": thread.channel,
                    "guest_name": thread.guest_name or "",
                    "text": thread.inbound_text or "",
                },
                timeout=12,
            )
        except Exception:  # noqa: BLE001
            _logger.exception("n8n escalate Créateur d'Expérience")

    def _room_rate(self, room, day=None):
        """Tarif publié configuré. Phase 1 n'écrit pas coins.channex.calendar."""
        return room.price_per_night or 0.0

    def _availability_lines(self, estab, start, days=7):
        dash = self.env["intellix.riad.dashboard"]
        rooms = estab.property_id.room_ids.filtered("active")
        end = start + timedelta(days=days)
        reservations = dash._reservations_in_range(estab.property_id.id, start, end)
        lines = []
        currency = estab.property_id.currency_id.symbol or "DH"
        for room in rooms:
            free_days = []
            day = start
            while day < end:
                taken = any(dash._occupies(resa, day) and resa.room_id == room for resa in reservations)
                if not taken:
                    free_days.append(day)
                day += timedelta(days=1)
            rate = self._room_rate(room, start)
            if free_days:
                first = free_days[0].strftime("%d/%m")
                lines.append(
                    "%s : libre dès le %s — %s %s / nuit%s"
                    % (
                        room.name,
                        first,
                        int(rate) if rate else "—",
                        currency,
                        " (PDJ inclus)" if room.breakfast_included else "",
                    )
                )
            else:
                lines.append("%s : complète sur les %s prochains jours" % (room.name, days))
        return lines

    def _practical_reply(self, estab):
        """Répond UNIQUEMENT avec la bibliothèque de cet établissement."""
        bits = []
        if estab.experience_neighborhood:
            bits.append(_("Quartier : %s") % estab.experience_neighborhood)
        checkin = estab.experience_checkin_hour or 14.0
        checkout = estab.experience_checkout_hour or 11.0
        bits.append(
            _("Check-in à partir de %sh%02d · check-out jusqu'à %sh%02d")
            % (int(checkin), int(round((checkin % 1) * 60)), int(checkout), int(round((checkout % 1) * 60)))
        )
        if estab.experience_howto:
            bits.append(estab.experience_howto)
        if estab.experience_wifi:
            bits.append(_("Wi‑Fi :\n%s") % estab.experience_wifi)
        if estab.experience_house_rules:
            bits.append(_("Règlement :\n%s") % estab.experience_house_rules)
        if estab.experience_useful_contacts:
            bits.append(_("Contacts utiles :\n%s") % estab.experience_useful_contacts)
        if estab.experience_local_tips:
            bits.append(_("Recommandations :\n%s") % estab.experience_local_tips)
        if estab.experience_facts:
            bits.append(estab.experience_facts)
        if not bits:
            return False
        return "\n\n".join(bits)

    def _wellness_reply(self, estab):
        Menu = self.env["intellix.riad.menu.item"]
        offers = Menu.catalog_for_establishment(estab, kind="wellness")
        start = estab.terrace_wellness_start or 10.0
        end = estab.terrace_wellness_end or 17.0
        staff = estab.practitioner_ids.filtered("active")
        people = ", ".join(staff.mapped("name")) if staff else _("sur demande")
        if offers:
            lines = []
            for row in offers:
                bit = row.name
                if row.duration_minutes:
                    bit = "%s (%s)" % (bit, row.duration_label())
                bit = "%s — %s" % (bit, row.price_label())
                lines.append(bit)
            catalog = "\n- ".join(lines)
            return _(
                "Menu des soins (société %s) :\n- %s\n"
                "Créneaux %sh–%sh, terrasse en mode transats / tables de massage, "
                "selon la présence de : %s. "
                "Indiquez le soin, le jour et l'heure — je réserve si le créneau est libre. "
                "Les clientes externes ne sont pas prises pendant une privatisation."
            ) % (estab.company_id.name or estab.name, catalog, int(start), int(end), people)
        types = estab.env["intellix.riad.wellness.type"].search([])
        names = ", ".join(types.mapped("name")) or _("massage, hammam, esthétique, brushing")
        return _(
            "Nous proposons : %s. "
            "Créneaux habituellement %sh–%sh, selon la présence de : %s. "
            "Indiquez le soin, le jour et l'heure souhaités — "
            "je réserve dès que le créneau est libre. "
            "Les clientes externes ne sont pas prises pendant une privatisation."
        ) % (names, int(start), int(end), people)

    def _restaurant_reply(self, estab):
        Menu = self.env["intellix.riad.menu.item"]
        mode = estab.current_space_mode()
        items = Menu.catalog_for_establishment(estab, kind="restaurant")
        if mode in ("wellness", "restaurant"):
            visible = items.filtered(lambda rec: rec.space_mode in (mode, "both"))
        else:
            visible = items
        r_start = estab.terrace_restaurant_start or 18.0
        r_end = estab.terrace_restaurant_end or 23.0
        w_end = estab.terrace_wellness_end or 17.0
        if not visible:
            return _(
                "La carte restaurant de %s n'est pas encore configurée. "
                "Anna vous répondra."
            ) % (estab.company_id.name or estab.name)
        lines = []
        for row in visible:
            extra = []
            if row.included_in_half_board:
                extra.append(_("inclus demi-pension"))
            extra.append(row.price_label())
            lines.append("%s — %s" % (row.name, " · ".join(extra)))
        if mode == "wellness":
            when = _(
                "En ce moment la terrasse est en mode transats / massage (jusqu'à %sh). "
                "Le service restaurant ouvre à %sh."
            ) % (int(w_end), int(r_start))
        elif mode == "restaurant":
            when = _("Service restaurant en cours jusqu'à %sh.") % int(r_end)
        else:
            when = _("Service restaurant %sh–%sh.") % (int(r_start), int(r_end))
        return _(
            "Carte restaurant / terrasse (société %s) :\n- %s\n%s"
        ) % (estab.company_id.name or estab.name, "\n- ".join(lines), when)

    def _draft_reply(self, estab, intent, text):
        today = fields.Date.context_today(self)
        if intent == "availability":
            lines = self._availability_lines(estab, today)
            return _("Disponibilités à jour :\n- %s") % "\n- ".join(lines)
        if intent == "rate":
            lines = []
            currency = estab.property_id.currency_id.symbol or "DH"
            for room in estab.property_id.room_ids.filtered("active"):
                rate = self._room_rate(room, today)
                lines.append(
                    "%s : %s %s / nuit%s"
                    % (
                        room.name,
                        int(rate) if rate else "—",
                        currency,
                        " (PDJ inclus)" if room.breakfast_included else "",
                    )
                )
            return _("Tarifs actuellement configurés :\n- %s") % "\n- ".join(lines)
        if intent == "practical":
            reply = self._practical_reply(estab)
            return reply or False
        if intent == "wellness":
            return self._wellness_reply(estab)
        if intent == "restaurant":
            return self._restaurant_reply(estab)
        return False

    def _maybe_polish(self, estab, reply):
        if not reply or not estab.experience_use_claude:
            return reply
        try:
            from odoo.addons.doorway_messaging.services.claude_service import (
                ClaudeMessagingService,
            )

            prompt = (
                "Reformule UNIQUEMENT le texte suivant, en français, ton hôtelier chaleureux. "
                "N'ajoute aucun fait, prix, horaire ou promesse. "
                "Si tu n'es pas sûr, redis le texte tel quel.\n\n%s" % reply
            )
            polished = ClaudeMessagingService(self.env)._call(prompt, max_tokens=400)
            if not polished:
                return reply
            return polished
        except Exception:  # noqa: BLE001
            _logger.exception("polish Créateur d'Expérience")
            return reply

    @api.model
    def cron_send_review_invites(self):
        today = fields.Date.context_today(self)
        for estab in self.env["intellix.riad.establishment"].search(
            [("experience_review_enabled", "=", True)]
        ):
            estab._send_due_review_invites(today)
        return True

    @api.model
    def seed_webhook_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("intellix_riad.experience_webhook_token"):
            import secrets

            icp.set_param(
                "intellix_riad.experience_webhook_token", secrets.token_urlsafe(24)
            )
        return True


class DoorwaySocialInboxRiadExperience(models.Model):
    _inherit = "doorway.social.inbox"

    def _handle_inbound(self, platform, external_id, content="", **kwargs):
        channel = super()._handle_inbound(
            platform, external_id, content=content, **kwargs
        )
        if not channel or not content or channel.ai_auto_reply:
            return channel
        agent = self.env["intellix.riad.experience.agent"]
        if not agent.should_handle_inbox(channel):
            return channel
        reply = agent.handle_inbox_message(channel, content)
        if reply:
            channel.action_send_message(reply)
        return channel

    def _claude_auto_reply(self, text):
        agent = self.env["intellix.riad.experience.agent"]
        if agent.should_handle_inbox(self):
            return agent.handle_inbox_message(self, text)
        return super()._claude_auto_reply(text)

    def action_send_message(self, text):
        res = super().action_send_message(text)
        threads = self.env["intellix.riad.experience.thread"].search(
            [
                ("inbox_id", "in", self.ids),
                ("decision", "=", "escalate"),
                ("replied_at", "=", False),
            ]
        )
        if threads:
            threads.action_mark_replied(text)
        return res
