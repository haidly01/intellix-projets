# -*- coding: utf-8 -*-
"""Avis clients réels — jamais fabriqués, jamais publiés sans validation."""
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

ASK_STATES = ("confirmed", "in_progress", "done")
EVENT_ASK_STATES = (
    "confirmed",
    "deposit_received",
    "day_j",
    "done",
    "invoiced",
)


class CoinsPropertyReview(models.Model):
    _name = "coins.property.review"
    _description = "Avis lieu (Coins Marocain)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(string="Référence", compute="_compute_name", store=True)
    property_id = fields.Many2one(
        "coins.property",
        string="Lieu",
        required=True,
        index=True,
        ondelete="cascade",
        tracking=True,
    )
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        index=True,
        ondelete="set null",
        copy=False,
    )
    evenement_id = fields.Many2one(
        "coins.evenement",
        string="Événement",
        index=True,
        ondelete="set null",
        copy=False,
    )
    traveler_id = fields.Many2one("res.partner", string="Voyageur", ondelete="set null")
    author_name = fields.Char(string="Prénom / nom affiché")
    phone = fields.Char(string="WhatsApp")
    texte = fields.Text(string="Avis")
    note = fields.Integer(string="Note / 5", help="Vide si le client n’a pas noté.")
    state = fields.Selection(
        [
            ("sollicite", "Sollicité"),
            ("a_valider", "À valider"),
            ("publie", "Publié"),
            ("refuse", "Refusé"),
        ],
        string="Statut",
        default="sollicite",
        required=True,
        tracking=True,
        index=True,
    )
    token = fields.Char(string="Jeton public", index=True, copy=False, readonly=True)
    asked_at = fields.Datetime(string="Sollicitation envoyée", readonly=True, copy=False)
    submitted_at = fields.Datetime(string="Avis reçu", readonly=True, copy=False)
    published_at = fields.Datetime(string="Publié le", readonly=True, copy=False)
    google_proposed_at = fields.Datetime(
        string="Lien Google proposé",
        readonly=True,
        copy=False,
    )
    ask_error = fields.Char(string="Erreur envoi", readonly=True, copy=False)
    is_test = fields.Boolean(string="Réservation de test", default=False, copy=False)
    source = fields.Selection(
        [("stay", "Séjour"), ("event", "Événement")],
        string="Origine",
        default="stay",
        required=True,
    )
    public_url = fields.Char(string="Lien avis", compute="_compute_public_url")
    google_review_url = fields.Char(
        related="property_id.google_review_url",
        readonly=True,
    )

    _sql_constraints = [
        ("token_uniq", "unique(token)", "Le jeton d’avis doit être unique."),
        (
            "reservation_uniq",
            "unique(reservation_id)",
            "Un seul avis par séjour — pas de relance.",
        ),
    ]

    @api.depends("property_id", "author_name", "reservation_id")
    def _compute_name(self):
        for rec in self:
            who = rec.author_name or (rec.reservation_id.name if rec.reservation_id else "")
            rec.name = " · ".join(x for x in [rec.property_id.name, who] if x) or _("Avis")

    def _compute_public_url(self):
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("coins_marocain.partenaire_base_url", "https://coinsmarocain.com")
            .rstrip("/")
        )
        for rec in self:
            rec.public_url = "%s/avis/%s" % (base, rec.token) if rec.token else ""

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not (vals.get("token") or "").strip():
                vals["token"] = secrets.token_urlsafe(24)
        return super().create(vals_list)

    @api.constrains("note")
    def _check_note(self):
        for rec in self:
            if rec.note and not (1 <= rec.note <= 5):
                raise ValidationError(_("La note doit être entre 1 et 5, ou vide."))

    def action_validate(self):
        """Publication humaine uniquement — jamais automatique."""
        for rec in self:
            if rec.state != "a_valider":
                raise UserError(
                    _("Seul un avis « à valider » peut être publié (pas une sollicitation vide).")
                )
            if not (rec.texte or "").strip():
                raise UserError(_("Impossible de publier un avis sans texte."))
            rec.write(
                {
                    "state": "publie",
                    "published_at": fields.Datetime.now(),
                }
            )
            rec.message_post(body=_("Avis publié sur la fiche. Rien n’a été inventé."))
        return True

    def action_refuse(self):
        self.write({"state": "refuse"})
        return True

    def action_reset_to_validate(self):
        for rec in self:
            if rec.state != "refuse":
                continue
            if (rec.texte or "").strip():
                rec.state = "a_valider"
        return True

    def action_propose_google(self):
        """Deuxième message, après validation : lien GBP si préparé. Pas une relance d’avis."""
        for rec in self:
            if rec.state != "publie":
                raise UserError(_("Proposer Google seulement après validation de l’avis."))
            url = (rec.google_review_url or "").strip()
            if not url:
                raise UserError(
                    _("Pas de fiche Google préparée pour ce lieu — champ à remplir à part.")
                )
            if rec.google_proposed_at:
                raise UserError(_("Le lien Google a déjà été proposé pour ce séjour."))
            phone = rec.phone or rec._phone_from_source()
            body = rec._google_wa_body(url)
            sent = rec._send_whatsapp(phone, body)
            rec.google_proposed_at = fields.Datetime.now()
            rec.message_post(
                body=_("Lien Google proposé%s.")
                % (" (envoi OK)" if sent.get("success") else " (envoi à revérifier)")
            )
        return True

    def submit_from_token(self, texte, author_name="", note=0):
        self.ensure_one()
        if self.state == "publie":
            raise UserError(_("Cet avis est déjà publié."))
        if self.state == "refuse":
            raise UserError(_("Cet avis a été refusé."))
        texte = (texte or "").strip()
        if len(texte) < 8:
            raise UserError(_("Écrivez quelques mots — un avis trop court n’aide personne."))
        vals = {
            "texte": texte[:4000],
            "author_name": (author_name or self.author_name or "").strip()[:80],
            "state": "a_valider",
            "submitted_at": fields.Datetime.now(),
        }
        if note:
            vals["note"] = int(note)
        self.write(vals)
        self.message_post(body=_("Avis reçu — en attente de validation Karine / Zakaria."))
        return True

    def _phone_from_source(self):
        self.ensure_one()
        if self.phone:
            return self.phone
        if self.reservation_id:
            return self.reservation_id._review_phone()
        if self.evenement_id:
            return self.evenement_id._review_phone()
        return ""

    def _ask_wa_body(self):
        self.ensure_one()
        name = (self.author_name or "").strip() or "bonjour"
        lieu = self.property_id.name or "votre lieu"
        return (
            "Bonjour %s,\n\n"
            "Merci pour votre séjour à %s. Un mot sincère de vous aide "
            "les prochains voyageurs — deux minutes, rien de plus.\n\n"
            "Laissez un avis ici : %s\n\n"
            "L’équipe Coins Marocain"
        ) % (name if name != "bonjour" else "", lieu, self.public_url)

    def _google_wa_body(self, url):
        self.ensure_one()
        return (
            "Merci — votre avis est en ligne sur Coins Marocain. "
            "Si vous le souhaitez, vous pouvez aussi le republier sur Google :\n%s"
        ) % url

    def _send_whatsapp(self, phone, body):
        """Réutilise Yasmine / n8n / Twilio — ne restructure pas les labels."""
        from odoo.addons.coins_marocain.services.yasmine_service import YasmineService

        svc = YasmineService(self.env)
        return svc.send_whatsapp(phone, body)

    def action_send_ask(self):
        """Envoie (ou renvoie si l’envoi a échoué). Jamais si déjà envoyé avec succès."""
        for rec in self:
            if rec.asked_at and not rec.ask_error:
                raise UserError(
                    _("Une sollicitation a déjà été envoyée pour ce séjour — pas de relance.")
                )
            phone = rec._phone_from_source()
            if not phone:
                raise UserError(_("Pas de numéro WhatsApp sur cette réservation."))
            rec.phone = phone
            body = rec._ask_wa_body()
            result = rec._send_whatsapp(phone, body)
            now = fields.Datetime.now()
            if result.get("success"):
                rec.write({"asked_at": now, "ask_error": False, "state": "sollicite"})
                if rec.reservation_id:
                    rec.reservation_id.review_ask_sent = True
                    rec.reservation_id.review_asked_at = now
                if rec.evenement_id:
                    rec.evenement_id.review_ask_sent = True
                    rec.evenement_id.review_asked_at = now
            else:
                rec.ask_error = (result.get("error") or "send_failed")[:250]
            rec.message_post(
                body=_("Sollicitation WhatsApp J+1%s:\n%s")
                % (
                    " envoyée" if result.get("success") else " tentée (échec canal)",
                    body,
                )
            )
        return True

    @api.model
    def cron_ask_reviews(self):
        """J+1 après check_out / date_end. Une seule tentative réussie par séjour."""
        today = fields.Date.context_today(self)
        cutoff = today - timedelta(days=1)
        oldest = today - timedelta(days=21)
        Reservation = self.env["coins.reservation"]
        resas = Reservation.search(
            [
                ("check_out", "<=", cutoff),
                ("check_out", ">=", oldest),
                ("state", "in", ASK_STATES),
                ("review_ask_sent", "=", False),
                ("is_demo", "=", False),
            ]
        )
        asked = 0
        for resa in resas:
            try:
                resa._ensure_review_and_ask()
                asked += 1
            except Exception:  # noqa: BLE001
                _logger.exception("avis J+1 reservation %s", resa.id)
        Event = self.env["coins.evenement"]
        events = Event.search(
            [
                ("date_end", "!=", False),
                ("state", "in", EVENT_ASK_STATES),
                ("review_ask_sent", "=", False),
                ("property_id", "!=", False),
            ]
        )
        for ev in events:
            end = fields.Date.to_date(ev.date_end)
            if not end or end > cutoff or end < oldest:
                continue
            try:
                ev._ensure_review_and_ask()
                asked += 1
            except Exception:  # noqa: BLE001
                _logger.exception("avis J+1 evenement %s", ev.id)
        return asked


class CoinsReservationReview(models.Model):
    _inherit = "coins.reservation"

    review_ask_sent = fields.Boolean(
        string="Avis déjà sollicité",
        default=False,
        copy=False,
        help="Une seule sollicitation WhatsApp par séjour.",
    )
    review_asked_at = fields.Datetime(string="Avis sollicité le", copy=False)
    review_ids = fields.One2many(
        "coins.property.review",
        "reservation_id",
        string="Avis",
    )

    def _review_phone(self):
        self.ensure_one()
        for raw in (
            self.client_telephone,
            self.traveler_id.phone if self.traveler_id else "",
            getattr(self.traveler_id, "mobile", None) if self.traveler_id else "",
        ):
            if raw and str(raw).strip():
                return str(raw).strip()
        return ""

    def _ensure_review_and_ask(self):
        self.ensure_one()
        if self.review_ask_sent:
            return self.review_ids[:1]
        existing = self.env["coins.property.review"].search(
            [("reservation_id", "=", self.id)], limit=1
        )
        if existing and existing.asked_at and not existing.ask_error:
            self.review_ask_sent = True
            return existing
        if not existing:
            existing = self.env["coins.property.review"].create(
                {
                    "property_id": self.property_id.id,
                    "reservation_id": self.id,
                    "traveler_id": self.traveler_id.id if self.traveler_id else False,
                    "author_name": self.client_nom or (self.traveler_id.name if self.traveler_id else ""),
                    "phone": self._review_phone(),
                    "source": "stay",
                    "is_test": bool(self.is_demo),
                    "state": "sollicite",
                }
            )
        existing.action_send_ask()
        return existing

    def action_ask_review_now(self):
        """Bouton manuel (tests ou rattrapage). Respecte le « une seule fois »."""
        for rec in self:
            rec._ensure_review_and_ask()
        return True


class CoinsEvenementReview(models.Model):
    _inherit = "coins.evenement"

    review_ask_sent = fields.Boolean(
        string="Avis déjà sollicité",
        default=False,
        copy=False,
    )
    review_asked_at = fields.Datetime(string="Avis sollicité le", copy=False)
    review_ids = fields.One2many(
        "coins.property.review",
        "evenement_id",
        string="Avis",
    )

    def _review_phone(self):
        self.ensure_one()
        for inv in self.invite_ids:
            if (inv.phone or "").strip():
                return inv.phone.strip()
        return ""

    def _ensure_review_and_ask(self):
        self.ensure_one()
        if self.review_ask_sent or not self.property_id:
            return self.review_ids[:1]
        existing = self.env["coins.property.review"].search(
            [("evenement_id", "=", self.id)], limit=1
        )
        if existing and existing.asked_at and not existing.ask_error:
            self.review_ask_sent = True
            return existing
        if not existing:
            existing = self.env["coins.property.review"].create(
                {
                    "property_id": self.property_id.id,
                    "evenement_id": self.id,
                    "author_name": self.name,
                    "phone": self._review_phone(),
                    "source": "event",
                    "state": "sollicite",
                }
            )
        existing.action_send_ask()
        return existing


class CoinsPropertyReviewLink(models.Model):
    _inherit = "coins.property"

    google_review_url = fields.Char(
        string="Lien avis Google (GBP)",
        help="Préparé à part. Vide = pas de republication Google proposée.",
    )
    review_ids = fields.One2many(
        "coins.property.review",
        "property_id",
        string="Avis clients",
    )

    def published_reviews(self):
        self.ensure_one()
        return self.review_ids.filtered(lambda r: r.state == "publie" and (r.texte or "").strip())
