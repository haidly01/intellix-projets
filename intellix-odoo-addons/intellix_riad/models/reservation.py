# -*- coding: utf-8 -*-

import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REFERRAL_KEYS = ("referral_code", "promo", "ref", "referral", "code")


class CoinsReservationRiad(models.Model):
    _inherit = "coins.reservation"

    demo_mark = fields.Char(
        string="Marquage démo",
        compute="_compute_demo_mark",
    )

    @api.depends("is_demo", "name")
    def _compute_demo_mark(self):
        for rec in self:
            rec.demo_mark = (
                "DÉMO CHANNNEX — données fictives, hors production"
                if rec.is_demo
                else ""
            )

    booking_channel = fields.Selection(
        selection_add=[
            ("riad_website", "Site du riad"),
        ],
        ondelete={"riad_website": "set default"},
    )
    room_emplacement = fields.Selection(
        related="room_id.emplacement",
        string="Emplacement chambre",
        readonly=True,
    )
    riad_privatisation_id = fields.Many2one(
        "intellix.riad.privatisation",
        string="Privatisation du riad",
        ondelete="set null",
        index=True,
    )
    room_rate = fields.Monetary(
        related="room_id.price_per_night",
        string="Tarif chambre / nuit",
        currency_field="currency_id",
        readonly=True,
    )
    riad_payment_transaction_id = fields.Many2one(
        "payment.transaction",
        string="Transaction paiement",
        copy=False,
        ondelete="set null",
    )
    riad_payment_state = fields.Selection(
        related="riad_payment_transaction_id.state",
        string="État paiement",
    )

    def _riad_payment_provider(self):
        self.ensure_one()
        estab = self._riad_establishment()
        return estab.payment_provider_id if estab else self.env["payment.provider"]

    def _riad_prepare_payment_transaction(self):
        """Capture manuelle : crée une transaction pending, sans encaissement auto."""
        if "payment.transaction" not in self.env:
            return self.env["payment.transaction"]
        Tx = self.env["payment.transaction"].sudo()
        created = Tx.browse()
        for rec in self:
            if rec.riad_payment_transaction_id:
                created |= rec.riad_payment_transaction_id
                continue
            provider = rec._riad_payment_provider()
            if not provider:
                continue
            amount = rec.amount_property or rec.amount_total or 0.0
            if amount <= 0:
                continue
            partner = rec.traveler_id
            vals = {
                "provider_id": provider.id,
                "amount": amount,
                "currency_id": rec.currency_id.id or rec.env.company.currency_id.id,
                "partner_id": partner.id,
                "reference": "RIAD-%s-%s" % (rec.id, rec.name or rec.id),
            }
            tx = Tx.create(vals)
            if hasattr(tx, "_set_pending"):
                try:
                    tx._set_pending()
                except Exception:
                    tx.write({"state": "pending"})
            rec.riad_payment_transaction_id = tx.id
            created |= tx
        return created

    def action_capture_payment(self):
        """Encaissement manuel — capture auto à la confirmation viendra plus tard."""
        self.ensure_one()
        if not self._riad_payment_provider():
            raise UserError(
                _("Connectez une passerelle dans Paramètres > Paiement "
                  "pour cet établissement.")
            )
        tx = self.riad_payment_transaction_id or self._riad_prepare_payment_transaction()
        if not tx:
            raise UserError(_("Montant à encaisser introuvable sur la réservation."))
        if tx.state in ("done", "authorized"):
            return True
        if hasattr(tx, "_send_capture_request"):
            try:
                tx._send_capture_request()
                return True
            except Exception:
                pass
        if hasattr(tx, "_set_done"):
            tx._set_done()
        else:
            tx.write({"state": "done"})
        self.message_post(body=_("Encaissement manuel enregistré (%s).") % tx.reference)
        return True

    riad_police_fiche_ids = fields.One2many(
        "intellix.riad.police.fiche",
        "reservation_id",
        string="Fiches de police",
    )
    riad_police_fiche_count = fields.Integer(compute="_compute_riad_compliance")
    riad_police_pending = fields.Integer(compute="_compute_riad_compliance")
    riad_guest_residency = fields.Selection(
        [
            ("unknown", "À préciser"),
            ("foreign", "Étranger (passeport)"),
            ("moroccan", "Résident marocain (CIN)"),
        ],
        string="Nationalité / pièce",
        default="unknown",
        tracking=True,
        help="La fiche de police DGSN ne concerne que les étrangers. "
        "La taxe de séjour s'applique à tous, sans ce filtre.",
    )
    riad_guest_nationality_id = fields.Many2one("res.country", string="Nationalité")
    riad_checkin_token = fields.Char(string="Token check-in", copy=False, index=True)
    riad_checkin_expiry = fields.Datetime(string="Expiration du lien", copy=False)
    riad_checkin_used_at = fields.Datetime(string="Lien utilisé le", copy=False)
    riad_police_status = fields.Char(
        string="Statut fiche de police",
        compute="_compute_riad_compliance",
    )
    riad_taxable_guests = fields.Integer(string="Personnes taxables")
    riad_tourist_tax_rate = fields.Float(
        string="Taux taxe de séjour",
        compute="_compute_riad_tourist_tax",
        store=True,
        digits=(16, 2),
    )
    riad_tax_currency_id = fields.Many2one(
        "res.currency",
        string="Devise taxe",
        compute="_compute_riad_tourist_tax",
        store=True,
    )
    riad_tourist_tax_amount = fields.Monetary(
        string="Taxe de séjour",
        currency_field="riad_tax_currency_id",
        compute="_compute_riad_tourist_tax",
        store=True,
        help="Montant séparé du prix de la chambre, en dirhams.",
    )
    riad_review_asked = fields.Boolean(
        string="Message post-séjour envoyé",
        default=False,
        copy=False,
    )
    riad_review_ota_thanks = fields.Boolean(
        string="Avis envoyé Booking/Airbnb",
        default=False,
        copy=False,
        help="Remerciement sans lien Google/Facebook : l'OTA gère déjà l'avis. "
        "La relance J+5 ne part jamais si ce flag est coché.",
    )
    riad_review_followup_sent = fields.Boolean(
        string="Relance avis J+5 envoyée",
        default=False,
        copy=False,
    )
    riad_referral_exported = fields.Boolean(
        string="Référence exportée (créateurs)",
        default=False,
        copy=False,
        help="Une seule écriture vers l'entente / webhook de versement. "
        "Pas de moteur de commission dans Module Hébergement.",
    )
    riad_ticket_ids = fields.One2many(
        "intellix.riad.table.ticket",
        "reservation_id",
        string="Additions restaurant",
    )
    riad_restaurant_note = fields.Monetary(
        string="Notes restaurant",
        currency_field="currency_id",
        compute="_compute_riad_restaurant_folio",
    )
    riad_restaurant_tip = fields.Monetary(
        string="Pourboires en chambre",
        currency_field="currency_id",
        compute="_compute_riad_restaurant_folio",
    )

    @api.depends(
        "riad_ticket_ids.amount",
        "riad_ticket_ids.tip_amount",
        "riad_ticket_ids.tip_mode",
        "riad_ticket_ids.state",
    )
    def _compute_riad_restaurant_folio(self):
        for rec in self:
            tickets = rec.riad_ticket_ids.filtered(lambda t: t.state == "charged")
            rec.riad_restaurant_note = sum(tickets.mapped("amount"))
            rec.riad_restaurant_tip = sum(
                t.tip_amount for t in tickets if t.tip_mode == "room"
            )

    def _room_stay_amount(self):
        self.ensure_one()
        if not self.room_id or not self.room_id.price_per_night:
            return None
        nights = self.nights
        if not nights and self.check_in and self.check_out:
            nights = (self.check_out - self.check_in).days
        if nights and nights > 0:
            return round(self.room_id.price_per_night * nights, 2)
        return None

    def _inject_room_defaults(self, vals):
        room_id = vals.get("room_id")
        if not room_id:
            return
        room = self.env["coins.property.room"].browse(room_id)
        if not room.exists():
            return
        if room.breakfast_included and "meal_breakfast" not in vals:
            vals["meal_breakfast"] = True
        if room.price_per_night and not vals.get("amount_property"):
            check_in = vals.get("check_in")
            check_out = vals.get("check_out")
            nights = 0
            if check_in and check_out:
                check_in = fields.Date.to_date(check_in)
                check_out = fields.Date.to_date(check_out)
                nights = (check_out - check_in).days
            if nights > 0:
                vals["amount_property"] = round(room.price_per_night * nights, 2)

    def _privatisation_blocks_stay(self, property_id, check_in, check_out, privatisation_id=None):
        if self.env.context.get("riad_skip_close_otas") or privatisation_id:
            return
        if not property_id or not check_in or not check_out:
            return
        check_in = fields.Date.to_date(check_in)
        check_out = fields.Date.to_date(check_out)
        last_night = check_out - timedelta(days=1)
        estab = self.env["intellix.riad.establishment"].search(
            [("property_id", "=", property_id)], limit=1
        )
        if not estab:
            return
        if self.env["intellix.riad.privatisation"].search_active(
            estab, check_in, last_night
        ):
            raise UserError(
                _(
                    "Le riad est en privatisation complète sur ces dates. "
                    "Aucune réservation de chambre séparée n'est possible "
                    "(site, OTA ou saisie manuelle)."
                )
            )

    @api.model
    def _normalize_referral_code(self, raw):
        text = (raw or "").strip()
        if not text:
            return ""
        if "://" in text or text.startswith("/") or "?" in text:
            parsed = urlparse(text)
            qs = parse_qs(parsed.query or "")
            for key in ("promo", "ref", "referral", "referral_code", "code"):
                values = qs.get(key) or []
                if values and values[0]:
                    return (values[0] or "").strip()
            slug = (parsed.path or "").rstrip("/").split("/")[-1]
            return (slug or "").strip()
        return text

    @api.model
    def _referral_from_http_request(self):
        try:
            from odoo.http import request

            httprequest = request.httprequest
            for key in REFERRAL_KEYS:
                value = httprequest.args.get(key)
                if value:
                    return self._normalize_referral_code(value)
            raw = httprequest.get_data(as_text=True) or ""
            if raw.startswith("{"):
                data = json.loads(raw)
                if isinstance(data, dict):
                    for key in REFERRAL_KEYS:
                        if data.get(key):
                            return self._normalize_referral_code(data.get(key))
        except Exception:  # noqa: BLE001
            return ""
        return ""

    def _inject_referral_code(self, vals):
        if vals.get("referral_code"):
            vals["referral_code"] = self._normalize_referral_code(vals["referral_code"])
            return
        from_request = self._referral_from_http_request()
        if from_request:
            vals["referral_code"] = from_request

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._inject_room_defaults(vals)
            self._inject_referral_code(vals)
            if not vals.get("riad_taxable_guests") and vals.get("voyageurs"):
                vals["riad_taxable_guests"] = vals["voyageurs"]
            self._privatisation_blocks_stay(
                vals.get("property_id"),
                vals.get("check_in"),
                vals.get("check_out"),
                vals.get("riad_privatisation_id"),
            )
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("check_in", "check_out", "property_id", "state")):
            for rec in self.filtered(lambda r: not r.riad_privatisation_id):
                rec._privatisation_blocks_stay(
                    rec.property_id.id, rec.check_in, rec.check_out
                )
        if any(k in vals for k in ("voyageurs", "state")):
            self.filtered(
                lambda r: r.state in ("confirmed", "in_progress")
            )._ensure_police_fiches()
        if any(k in vals for k in ("riad_guest_residency", "riad_guest_nationality_id")):
            self._sync_police_residency()
        return res

    def _flush_channex_now(self):
        """Même mécanisme que la privatisation : file Channex tout de suite.

        `_close_otas` n'enqueue que. Sans flush, le cron 15 min laisse une
        fenêtre de double réservation OTA (classement Booking).
        Jamais de full sync ici.
        """
        if self.env.context.get("riad_skip_close_otas"):
            return
        Push = self.env["coins.channex.push"]
        if hasattr(Push, "cron_flush"):
            Push.cron_flush()

    def _on_confirmed(self):
        if self.env.context.get("riad_skip_close_otas"):
            self._export_creator_referral()
            return True
        res = super()._on_confirmed()
        directs = self.filtered(
            lambda r: not (hasattr(r, "_is_ota_source") and r._is_ota_source())
        )
        if directs:
            directs._flush_channex_now()
        self._export_creator_referral()
        return res

    def action_confirm_website_booking(self):
        res = super().action_confirm_website_booking()
        self._flush_channex_now()
        self._export_creator_referral()
        return res

    @api.onchange("room_id", "check_in", "check_out")
    def _onchange_room_rate(self):
        for rec in self:
            if rec.room_id and rec.room_id.breakfast_included:
                rec.meal_breakfast = True
            amount = rec._room_stay_amount()
            if amount is not None:
                rec.amount_property = amount

    def _riad_establishment(self):
        self.ensure_one()
        if not self.property_id:
            return self.env["intellix.riad.establishment"]
        return self.env["intellix.riad.establishment"].search(
            [("property_id", "=", self.property_id.id)], limit=1
        )

    @api.depends(
        "riad_police_fiche_ids",
        "riad_police_fiche_ids.state",
        "riad_police_fiche_ids.is_moroccan",
        "riad_guest_residency",
        "riad_guest_nationality_id",
        "riad_checkin_token",
        "riad_checkin_used_at",
    )
    def _compute_riad_compliance(self):
        for rec in self:
            fiches = rec.riad_police_fiche_ids
            rec.riad_police_fiche_count = len(fiches)
            rec.riad_police_pending = len(
                fiches.filtered(
                    lambda f: f.state in ("draft", "ready") and not f.is_moroccan
                )
            )
            if rec._riad_is_moroccan_guest():
                rec.riad_police_status = "Non applicable (résident marocain)"
            elif fiches.filtered(lambda f: f.state in ("completed", "exported")):
                rec.riad_police_status = "Fiche complétée"
            elif rec.riad_checkin_token and not rec.riad_checkin_used_at:
                rec.riad_police_status = "Lien de check-in envoyé"
            elif rec.riad_police_pending:
                rec.riad_police_status = "À compléter"
            else:
                rec.riad_police_status = "—"

    @api.depends(
        "voyageurs",
        "riad_taxable_guests",
        "nights",
        "check_in",
        "check_out",
        "property_id",
    )
    def _compute_riad_tourist_tax(self):
        # Taxe de séjour : tous les voyageurs, y compris les résidents marocains.
        # Ne jamais lire riad_guest_residency / nationality ici.
        mad = self.env["res.currency"].search([("name", "=", "MAD")], limit=1)
        for rec in self:
            estab = rec._riad_establishment() if rec.property_id else False
            rec.riad_tax_currency_id = (
                (estab.tourist_tax_currency_id.id if estab and estab.tourist_tax_currency_id else False)
                or (mad.id if mad else rec.currency_id.id)
            )
            rate = estab.tourist_tax_rate if estab else 0.0
            rec.riad_tourist_tax_rate = rate
            guests = rec.riad_taxable_guests or rec.voyageurs or 0
            nights = rec.nights or 0
            rec.riad_tourist_tax_amount = round(guests * nights * (rate or 0.0), 2)

    def _riad_is_moroccan_guest(self):
        """Filtre fiche de police uniquement — jamais la taxe de séjour."""
        self.ensure_one()
        if self.riad_guest_residency == "moroccan":
            return True
        code = (self.riad_guest_nationality_id.code or "").upper()
        if code == "MA":
            return True
        fiches = self.riad_police_fiche_ids
        if fiches and all(fiches.mapped("is_moroccan")):
            return True
        return False

    def _riad_skip_google_facebook_review(self):
        """Booking / Airbnb (source ou canal OTA) : pas de demande d'avis Google/Facebook."""
        self.ensure_one()
        source = (self.source or "").strip().lower()
        if source in ("booking", "airbnb"):
            return True
        if hasattr(self, "_is_ota_source") and self._is_ota_source():
            return True
        channel = (self.booking_channel or "").strip().lower()
        return channel == "ota"

    def _guest_contact(self):
        self.ensure_one()
        email = self.client_email or (
            self.traveler_id.email if self.traveler_id else ""
        )
        phone = self.client_telephone or (
            self.traveler_id.phone if self.traveler_id else ""
        )
        name = self.client_nom or (
            self.traveler_id.name if self.traveler_id else ""
        )
        return (email or "").strip(), (phone or "").strip(), (name or "").strip()

    def _checkin_public_url(self):
        self.ensure_one()
        base = self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url", "https://intellixcrm.com"
        )
        return "%s/checkin/%s" % (base.rstrip("/"), self.riad_checkin_token or "")

    def _sync_police_residency(self):
        """Propage CIN / passeport vers les fiches. N'efface pas la taxe."""
        morocco = self.env["res.country"].search([("code", "=", "MA")], limit=1)
        for rec in self:
            if rec._riad_is_moroccan_guest():
                vals = {"id_document_type": "cin"}
                country = rec.riad_guest_nationality_id or morocco
                if country:
                    vals["nationality_id"] = country.id
                if rec.riad_police_fiche_ids:
                    rec.riad_police_fiche_ids.write(vals)
                if rec.riad_checkin_token and not rec.riad_checkin_used_at:
                    rec.riad_checkin_used_at = fields.Datetime.now()
            elif rec.riad_guest_residency == "foreign":
                vals = {"id_document_type": "passport"}
                if rec.riad_guest_nationality_id:
                    vals["nationality_id"] = rec.riad_guest_nationality_id.id
                rec.riad_police_fiche_ids.filtered(
                    lambda f: f.state not in ("completed", "exported")
                ).write(vals)

    def _prepare_checkin_token(self):
        """Génère le token seulement si la fiche de police s'applique (non-MA)."""
        self.ensure_one()
        if self._riad_is_moroccan_guest():
            raise UserError(
                _(
                    "Résident marocain : pas de fiche de police, donc pas de lien "
                    "de check-in. La taxe de séjour reste due."
                )
            )
        token = secrets.token_urlsafe(32)
        self.write(
            {
                "riad_checkin_token": token,
                "riad_checkin_expiry": fields.Datetime.now() + timedelta(days=14),
                "riad_checkin_used_at": False,
            }
        )
        return token

    def action_send_checkin_link(self):
        """Envoie le lien self-service via doorway_messaging (email + WhatsApp)."""
        from odoo.addons.doorway_messaging.services.email_service import EmailService

        for rec in self:
            if rec._riad_is_moroccan_guest():
                raise UserError(
                    _(
                        "Pas de lien fiche de police pour %s : résident marocain. "
                        "La taxe de séjour n'est pas affectée."
                    )
                    % (rec.client_nom or rec.name)
                )
            rec._ensure_police_fiches()
            rec._prepare_checkin_token()
            email, phone, name = rec._guest_contact()
            if not email and not phone:
                raise UserError(
                    _("Indiquez un email ou un WhatsApp avant d'envoyer le lien.")
                )
            url = rec._checkin_public_url()
            estab = rec._riad_establishment()
            house = estab.name if estab else (rec.property_id.name or "")
            subject = _("Check-in — fiche de police — %s") % house
            html = (
                "<html><body style='font-family:Georgia,serif;color:#241A12;"
                "background:#FBF7EF;padding:24px;'>"
                "<p>%s</p>"
                "<p>%s</p>"
                "<p><a href='%s' style='display:inline-block;padding:14px 22px;"
                "background:#145C42;color:#FBF7EF;text-decoration:none;"
                "border-radius:12px;'>%s</a></p>"
                "<p>%s → %s</p>"
                "</body></html>"
            ) % (
                _("Bonjour %s,") % (name or ""),
                _("Merci de compléter votre fiche avant l'arrivée, depuis votre téléphone."),
                url,
                _("Ouvrir ma fiche"),
                rec.check_in or "",
                rec.check_out or "",
            )
            sent = False
            if email:
                result = EmailService(rec.env).send_email(
                    email, subject, html, recipient_name=name or ""
                )
                sent = bool(result.get("success"))
                if not sent:
                    _logger.warning("Check-in email %s: %s", rec.id, result.get("error"))
            if phone:
                try:
                    from odoo.addons.doorway_messaging.services.whatsapp_service import (
                        WhatsAppService,
                    )

                    wa = WhatsAppService(rec.env).send_whatsapp(
                        to_number=phone,
                        body=_("%s — votre fiche d'arrivée : %s") % (house, url),
                    )
                    sent = sent or bool(wa.get("success"))
                except Exception:
                    _logger.exception("Check-in WhatsApp %s", rec.id)
            if not sent:
                raise UserError(_("L'envoi du lien a échoué. Vérifiez email / WhatsApp."))
            rec.message_post(body=_("Lien de check-in envoyé : %s") % url)
        return True

    @api.model
    def cron_police_checkin_reminder(self):
        """Alerte 24 h avant arrivée si la fiche étrangère n'est pas complétée."""
        tomorrow = fields.Date.context_today(self) + timedelta(days=1)
        stays = self.search(
            [
                ("check_in", "=", tomorrow),
                ("state", "in", ("confirmed", "in_progress")),
                ("riad_privatisation_id", "=", False),
            ]
        )
        from odoo.addons.doorway_messaging.services.email_service import EmailService

        mailer = EmailService(self.env)
        for rec in stays:
            if rec._riad_is_moroccan_guest():
                continue
            pending = rec.riad_police_fiche_ids.filtered(
                lambda f: not f.is_moroccan and f.state in ("draft", "ready")
            )
            if not pending and rec.riad_checkin_used_at:
                continue
            if rec.riad_police_fiche_ids.filtered(
                lambda f: f.state in ("completed", "exported")
            ) and not pending:
                continue
            estab = rec._riad_establishment()
            dest = ""
            dest_name = ""
            if estab:
                dest, dest_name = estab._tax_report_recipient()
            guest_email, _phone, guest_name = rec._guest_contact()
            subject = _("Fiche de police manquante — arrivée demain — %s") % (
                rec.client_nom or rec.name
            )
            body = (
                "<p>%s</p><p>%s → %s</p>"
                % (
                    _("La fiche de police n'est pas encore signée (délai DGSN 24 h)."),
                    rec.check_in,
                    rec.check_out,
                )
            )
            if dest:
                mailer.send_email(dest, subject, body, recipient_name=dest_name or "")
            if guest_email and rec.riad_checkin_token and not rec.riad_checkin_used_at:
                mailer.send_email(
                    guest_email,
                    _("Rappel — votre fiche d'arrivée"),
                    body + "<p><a href='%s'>%s</a></p>"
                    % (rec._checkin_public_url(), _("Compléter maintenant")),
                    recipient_name=guest_name or "",
                )
            rec.message_post(body=subject)
        return True

    def expire_checkin_token(self):
        for rec in self:
            rec.riad_checkin_used_at = fields.Datetime.now()
        return True

    def _split_client_name(self):
        self.ensure_one()
        raw = (self.client_nom or self.traveler_id.name or "").strip()
        if not raw:
            return "", ""
        parts = raw.split(None, 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[-1], parts[0]

    def _ensure_police_fiches(self):
        Fiche = self.env["intellix.riad.police.fiche"]
        for rec in self:
            if rec.riad_privatisation_id:
                continue
            estab = rec._riad_establishment()
            if not estab:
                continue
            if rec._riad_is_moroccan_guest():
                rec._sync_police_residency()
                continue
            needed = max(int(rec.voyageurs or 1), 1)
            existing = rec.riad_police_fiche_ids.sorted("sequence")
            lastname, firstname = rec._split_client_name()
            for index in range(1, needed + 1):
                hit = existing.filtered(lambda f, i=index: f.sequence == i)[:1]
                if hit:
                    continue
                vals = {
                    "establishment_id": estab.id,
                    "reservation_id": rec.id,
                    "sequence": index,
                    "phone": rec.client_telephone or rec.traveler_id.phone or "",
                    "email": rec.client_email or rec.traveler_id.email or "",
                    "entry_date": rec.check_in,
                    "nationality_id": rec.riad_guest_nationality_id.id or False,
                    "id_document_type": (
                        "cin"
                        if rec.riad_guest_residency == "moroccan"
                        else "passport"
                        if rec.riad_guest_residency == "foreign"
                        else False
                    ),
                }
                if index == 1:
                    vals["lastname"] = lastname
                    vals["firstname"] = firstname
                Fiche.create(vals)

    def action_prepare_police_fiches(self):
        self._ensure_police_fiches()
        return True

    def action_print_police_fiches(self):
        self._ensure_police_fiches()
        fiches = self.mapped("riad_police_fiche_ids")
        return fiches.action_print()

    def action_confirm(self):
        if self.env.context.get("riad_skip_close_otas"):
            self.write({"state": "confirmed"})
            self._ensure_police_fiches()
            self._export_creator_referral()
            self._riad_prepare_payment_transaction()
            return True
        res = super().action_confirm()
        self._ensure_police_fiches()
        self._export_creator_referral()
        self._riad_prepare_payment_transaction()
        return res

    def _referral_code_value(self):
        self.ensure_one()
        return self._normalize_referral_code(self.referral_code)

    def _find_entente_for_code(self, code):
        if not code or "coins.entente" not in self.env:
            return self.env["coins.entente"] if "coins.entente" in self.env else False
        Entente = self.env["coins.entente"].sudo()
        domain = [
            ("code_promo", "=ilike", code),
            ("active", "=", True),
        ]
        if "statut_entente" in Entente._fields:
            domain.append(("statut_entente", "=", "active"))
        return Entente.search(domain, limit=1)

    def _record_entente_activation(self, code, amount):
        self.ensure_one()
        entente = self._find_entente_for_code(code)
        if not entente:
            return False
        Activation = self.env["coins.entente.activation"].sudo()
        note = "Hébergement %s" % (self.name or self.id)
        existing = Activation.search(
            [
                ("entente_id", "=", entente.id),
                ("note", "=", note),
            ],
            limit=1,
        )
        if existing:
            return existing
        return Activation.create(
            {
                "entente_id": entente.id,
                "date": fields.Date.context_today(self),
                "montant": amount or 0.0,
                "note": note,
            }
        )

    def _record_ambassador_referral(self, code, amount):
        self.ensure_one()
        if "coins.ambassador" not in self.env:
            return False
        Amb = self.env["coins.ambassador"].sudo()
        amb = Amb.search([("code_parrainage", "=ilike", code)], limit=1)
        if not amb or not amb.partner_id:
            return False
        Referral = self.env["coins.ambassador.referral"].sudo()
        existing = Referral.search(
            [
                ("ambassador_id", "=", amb.id),
                ("reservation_id", "=", self.id),
            ],
            limit=1,
        )
        if existing:
            return existing
        rate = amb.taux_commission or 5.0
        return Referral.create(
            {
                "ambassador_id": amb.id,
                "referrer_partner_id": amb.partner_id.id,
                "reservation_id": self.id,
                "name": self.name or code,
                "booking_amount": amount or 0.0,
                "montant": round((amount or 0.0) * (rate / 100.0), 2),
                "statut_commission": "pending",
                "notes": "Module Hébergement — parrainage créateur",
            }
        )

    def _notify_creator_payout_webhook(self, estab, code, amount, activation):
        self.ensure_one()
        url = (estab.creator_payout_webhook or "").strip()
        if not url:
            return
        try:
            import requests

            requests.post(
                url,
                json={
                    "event": "riad_referral",
                    "referral_code": code,
                    "reservation_id": self.id,
                    "reservation_name": self.name or "",
                    "amount": amount or 0.0,
                    "currency": self.currency_id.name or "EUR",
                    "commission_pct": estab.creator_commission_pct or 5.0,
                    "compensation": estab.creator_compensation
                    or "experience_commission",
                    "establishment_id": estab.id,
                    "establishment_name": estab.name or "",
                    "property_id": self.property_id.id if self.property_id else False,
                    "nights": self.nights or 0,
                    "guests": self.voyageurs or 0,
                    "check_in": str(self.check_in or ""),
                    "check_out": str(self.check_out or ""),
                    "guest_name": self.client_nom or "",
                    "entente_activation_id": activation.id if activation else False,
                    "entente_id": activation.entente_id.id if activation else False,
                },
                timeout=12,
            )
        except Exception:  # noqa: BLE001
            _logger.exception(
                "Webhook versement créateurs — réservation %s", self.id
            )

    def _export_creator_referral(self):
        """Champ source + export vers le versement existant. Pas de back-office fusionné."""
        for rec in self:
            if rec.riad_referral_exported:
                continue
            if rec.state not in ("confirmed", "in_progress", "done"):
                continue
            code = rec._referral_code_value()
            if not code:
                continue
            estab = rec._riad_establishment()
            if not estab:
                continue
            amount = rec.amount_property or 0.0
            activation = rec._record_entente_activation(code, amount)
            rec._record_ambassador_referral(code, amount)
            rec._notify_creator_payout_webhook(estab, code, amount, activation)
            rec.riad_referral_exported = True
            rec.message_post(
                body=_("Code de référence %s exporté vers le versement créateurs.")
                % code
            )
