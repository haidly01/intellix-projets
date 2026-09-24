# -*- coding: utf-8 -*-

"""Tarification dynamique — Phase 1 (visibilité).

Saisie manuelle depuis Booking Analytics (Pace) et Airbnb Insights.
Pas de scraping, pas d'écriture coins.channex.calendar (pont Phase 2).
"""

import logging
from datetime import timedelta
from statistics import median

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MAX_COMP_SET = 10
SNAPSHOT_STALE_DAYS = 7


class IntellixRiadCompRiad(models.Model):
    _name = "intellix.riad.comp.riad"
    _description = "Riad comparable (comp-set)"
    _order = "sequence, name"

    name = fields.Char(string="Nom du riad comparable", required=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_kind = fields.Selection(
        [
            ("booking_analytics", "Booking Analytics (Pace)"),
            ("airbnb_insights", "Airbnb Insights"),
            ("both", "Booking + Airbnb"),
        ],
        string="Source officielle",
        required=True,
        default="both",
        help="Extraits du compte hôte uniquement. Jamais de scraping.",
    )
    booking_label = fields.Char(
        string="Libellé Booking Analytics",
        help="Nom tel qu'il apparaît dans le rapport Pace (jusqu'à 10 concurrents).",
    )
    airbnb_label = fields.Char(
        string="Libellé Airbnb Insights",
        help="Nom tel qu'il apparaît dans Informations du compte hôte.",
    )
    notes = fields.Text(
        string="Notes",
        help="Pourquoi ce riad est comparable (quartier, taille, standing).",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    rate_ids = fields.One2many(
        "intellix.riad.comp.rate",
        "competitor_id",
        string="Saisies",
    )
    last_rate = fields.Monetary(
        compute="_compute_last_rate",
        string="Dernier tarif observé",
        currency_field="currency_id",
    )
    last_observed_on = fields.Date(compute="_compute_last_rate", string="Dernière saisie")
    currency_id = fields.Many2one(
        related="establishment_id.property_id.currency_id",
        readonly=True,
    )

    @api.depends("rate_ids.their_rate", "rate_ids.observed_on")
    def _compute_last_rate(self):
        for rec in self:
            latest = rec.rate_ids.sorted("observed_on", reverse=True)[:1]
            rec.last_rate = latest.their_rate if latest else 0.0
            rec.last_observed_on = latest.observed_on if latest else False

    @api.constrains("establishment_id", "active")
    def _check_comp_set_size(self):
        for rec in self:
            if not rec.establishment_id:
                continue
            count = self.search_count(
                [
                    ("establishment_id", "=", rec.establishment_id.id),
                    ("active", "=", True),
                ]
            )
            if count > MAX_COMP_SET:
                raise ValidationError(
                    _(
                        "Le comp-set est limité à %s riads (plafond Booking Analytics). "
                        "Archivez un comparable avant d'en ajouter un."
                    )
                    % MAX_COMP_SET
                )


class IntellixRiadCompRate(models.Model):
    _name = "intellix.riad.comp.rate"
    _description = "Saisie tarif comparable (manuelle)"
    _order = "observed_on desc, id desc"
    _inherit = ["mail.thread"]

    competitor_id = fields.Many2one(
        "intellix.riad.comp.riad",
        string="Riad comparable",
        required=True,
        ondelete="cascade",
        index=True,
    )
    establishment_id = fields.Many2one(
        related="competitor_id.establishment_id",
        store=True,
        index=True,
    )
    observed_on = fields.Date(
        string="Date de l'extrait",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_from = fields.Date(string="Séjour dès (optionnel)")
    date_to = fields.Date(string="Séjour jusqu'à (optionnel)")
    stay_nights = fields.Integer(string="Nuits de référence", default=1)
    their_rate = fields.Monetary(
        string="Tarif observé (eux)",
        required=True,
        currency_field="currency_id",
        tracking=True,
    )
    our_rate = fields.Monetary(
        string="Notre tarif (référence)",
        currency_field="currency_id",
        tracking=True,
        help="Prérempli avec le tarif de référence de l'établissement. Modifiable.",
    )
    currency_id = fields.Many2one(
        related="establishment_id.property_id.currency_id",
        readonly=True,
    )
    source = fields.Selection(
        [
            ("booking_pace", "Booking Analytics — Pace"),
            ("airbnb_insights", "Airbnb Insights"),
            ("manual", "Saisie manuelle (autre extrait officiel)"),
        ],
        string="Source",
        required=True,
        default="booking_pace",
    )
    notes = fields.Char(string="Précision (type chambre, saison…)")
    gap_percent = fields.Float(
        string="Écart % (nous vs eux)",
        compute="_compute_gap",
        store=True,
        help="Positif = nous plus chers. Négatif = nous moins chers.",
    )
    alert_sent = fields.Boolean(string="Alerte envoyée", readonly=True)
    entered_by = fields.Many2one(
        "res.users",
        string="Saisi par",
        default=lambda self: self.env.user,
        readonly=True,
    )

    @api.depends("their_rate", "our_rate")
    def _compute_gap(self):
        for rec in self:
            if rec.their_rate:
                rec.gap_percent = ((rec.our_rate or 0.0) - rec.their_rate) / rec.their_rate * 100.0
            else:
                rec.gap_percent = 0.0

    @api.onchange("competitor_id")
    def _onchange_fill_our_rate(self):
        for rec in self:
            if rec.competitor_id and rec.establishment_id and not rec.our_rate:
                rec.our_rate = rec.establishment_id.reference_night_rate()

    @api.model_create_multi
    def create(self, vals_list):
        Comp = self.env["intellix.riad.comp.riad"]
        Estab = self.env["intellix.riad.establishment"]
        for vals in vals_list:
            if not vals.get("our_rate"):
                competitor = Comp.browse(vals.get("competitor_id"))
                estab = competitor.establishment_id or Estab.browse(
                    vals.get("establishment_id")
                )
                if estab:
                    vals["our_rate"] = estab.reference_night_rate()
        records = super().create(vals_list)
        records._maybe_alert()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("their_rate", "our_rate")):
            self.filtered(lambda r: not r.alert_sent)._maybe_alert()
        return res

    def _maybe_alert(self):
        for rec in self:
            estab = rec.establishment_id
            if not estab or not estab.pricing_alert_enabled:
                continue
            threshold = estab.pricing_gap_threshold or 10.0
            if abs(rec.gap_percent or 0.0) < threshold:
                continue
            rec._send_gap_alert()

    def _send_gap_alert(self):
        self.ensure_one()
        estab = self.establishment_id
        email = estab.pricing_alert_email_resolved()
        direction = (
            _("plus cher")
            if self.gap_percent > 0
            else _("moins cher")
        )
        subject = _(
            "[%s] Écart tarif vs %s : %s%s %% (%s)"
        ) % (
            estab.name or _("Riad"),
            self.competitor_id.name,
            "+" if self.gap_percent > 0 else "",
            int(round(self.gap_percent)),
            direction,
        )
        html = self._alert_html(estab, direction)
        if email:
            try:
                from odoo.addons.doorway_messaging.services.email_service import (
                    EmailService,
                )

                result = EmailService(self.env).send_email(
                    email,
                    subject,
                    html,
                    recipient_name=estab.name or "",
                )
                if not result.get("success"):
                    _logger.warning(
                        "Alerte tarif e-mail échouée : %s", result.get("error")
                    )
            except Exception:  # noqa: BLE001
                _logger.exception("Alerte tarif e-mail")
        estab._notify_pricing_n8n(self)
        estab.activity_schedule(
            "mail.mail_activity_data_todo",
            summary=subject,
            note=html,
        )
        self.alert_sent = True
        estab.pricing_last_alert_at = fields.Datetime.now()

    def _alert_html(self, estab, direction):
        self.ensure_one()
        currency = self.currency_id.symbol or "DH"
        return (
            "<html><body style='font-family:Georgia,serif;color:#241A12'>"
            "<p>Saisie manuelle — source officielle : <b>%s</b>.</p>"
            "<p>Nous sommes <b>%s</b> que <b>%s</b> "
            "(seuil d'alerte : %s %%).</p>"
            "<table cellpadding='8' style='border-collapse:collapse'>"
            "<tr><td>Notre tarif</td><td><b>%s %s</b></td></tr>"
            "<tr><td>Leur tarif</td><td><b>%s %s</b></td></tr>"
            "<tr><td>Écart</td><td><b>%s %%</b></td></tr>"
            "<tr><td>Extrait du</td><td>%s</td></tr>"
            "</table>"
            "<p style='color:#9C9280;font-size:12px'>"
            "Phase 1 : visibilité seulement. Aucun prix n'a été poussé vers "
            "Channex / Booking / Airbnb. Pas de scraping.</p>"
            "</body></html>"
        ) % (
            dict(self._fields["source"].selection).get(self.source) or self.source,
            direction,
            self.competitor_id.name,
            int(estab.pricing_gap_threshold or 10),
            int(round(self.our_rate or 0)),
            currency,
            int(round(self.their_rate or 0)),
            currency,
            int(round(self.gap_percent or 0)),
            self.observed_on,
        )


class IntellixRiadEstablishment(models.Model):
    _inherit = "intellix.riad.establishment"

    pricing_alert_enabled = fields.Boolean(
        string="Alertes écart tarif (Phase 1)",
        default=True,
        help="E-mail + n8n à chaque saisie hors seuil. "
        "Aucune écriture automatique vers Channex.",
    )
    pricing_gap_threshold = fields.Float(
        string="Seuil d'écart (%)",
        default=10.0,
        help="Alerte si |notre tarif − comparable| / comparable ≥ ce pourcentage.",
    )
    pricing_currency_id = fields.Many2one(
        related="property_id.currency_id",
        readonly=True,
    )
    pricing_our_reference_rate = fields.Monetary(
        string="Notre tarif de référence (nuit)",
        currency_field="pricing_currency_id",
        help="Si vide : plus bas tarif chambre configuré. "
        "Phase 1 ne pousse pas ce montant vers les OTA.",
    )
    pricing_alert_email = fields.Char(
        string="E-mail alertes tarif",
        help="Sinon : e-mail taxe de séjour, puis e-mail comptable.",
    )
    pricing_n8n_webhook = fields.Char(
        string="Webhook n8n (écarts tarif)",
        help="Même pattern que le Créateur d'Expérience. "
        "Le workflow n8n envoie le courriel si l'e-mail Odoo n'est pas utilisé.",
    )
    pricing_last_alert_at = fields.Datetime(
        string="Dernière alerte tarif",
        readonly=True,
    )
    pricing_last_reminder_on = fields.Date(
        string="Dernier rappel de saisie",
        readonly=True,
    )
    comp_riad_ids = fields.One2many(
        "intellix.riad.comp.riad",
        "establishment_id",
        string="Comp-set",
    )
    pricing_rate_ids = fields.One2many(
        "intellix.riad.comp.rate",
        "establishment_id",
        string="Saisies tarifaires",
    )

    def reference_night_rate(self):
        self.ensure_one()
        if self.pricing_our_reference_rate:
            return self.pricing_our_reference_rate
        rooms = self.property_id.room_ids.filtered(
            lambda r: r.active and r.price_per_night
        )
        if not rooms:
            return 0.0
        return min(rooms.mapped("price_per_night"))

    def pricing_alert_email_resolved(self):
        self.ensure_one()
        return (
            (self.pricing_alert_email or "").strip()
            or (self.tax_report_email or "").strip()
            or (self.payroll_accountant_email or "").strip()
        )

    def _notify_pricing_n8n(self, rate):
        self.ensure_one()
        url = (self.pricing_n8n_webhook or "").strip()
        if not url:
            return
        try:
            import requests

            requests.post(
                url,
                json={
                    "event": "pricing_gap",
                    "establishment_id": self.id,
                    "establishment_name": self.name or "",
                    "competitor": rate.competitor_id.name,
                    "source": rate.source,
                    "our_rate": rate.our_rate,
                    "their_rate": rate.their_rate,
                    "gap_percent": rate.gap_percent,
                    "observed_on": str(rate.observed_on or ""),
                    "currency": rate.currency_id.name or "MAD",
                },
                timeout=12,
            )
        except Exception:  # noqa: BLE001
            _logger.exception("n8n alerte tarif Phase 1")

    def pricing_dashboard_payload(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        competitors = self.comp_riad_ids.filtered("active")
        recent = self.pricing_rate_ids.filtered(
            lambda r: r.observed_on
            and r.observed_on >= today - timedelta(days=14)
        )
        latest_per = {}
        for rate in recent.sorted("observed_on", reverse=True):
            latest_per.setdefault(rate.competitor_id.id, rate)
        gaps = [r.gap_percent for r in latest_per.values()]
        last_on = max((r.observed_on for r in latest_per.values()), default=False)
        stale = (not last_on) or (today - last_on).days >= SNAPSHOT_STALE_DAYS
        if not competitors:
            return {
                "label": "—",
                "sub": _("Comp-set vide — 5 à 10 riads comparables"),
                "css": "",
                "stale": True,
            }
        if not gaps:
            return {
                "label": "—",
                "sub": _("Saisir un extrait Booking Analytics / Airbnb Insights"),
                "css": "warn",
                "stale": True,
            }
        mid = median(gaps)
        sign = "+" if mid > 0 else ""
        threshold = self.pricing_gap_threshold or 10.0
        if stale:
            css = "warn"
        elif abs(mid) >= threshold:
            css = "bad"
        else:
            css = "ok"
        return {
            "label": _("%s%s %% vs médiane") % (sign, int(round(mid))),
            "sub": _("%s riads · saisie %s")
            % (len(competitors), last_on.strftime("%d/%m") if last_on else "—"),
            "css": css,
            "stale": stale,
        }

    @api.model
    def cron_pricing_weekly_reminder(self):
        today = fields.Date.context_today(self)
        for estab in self.search([("pricing_alert_enabled", "=", True)]):
            if estab.pricing_last_reminder_on == today:
                continue
            if not estab.comp_riad_ids.filtered("active"):
                continue
            last = estab.pricing_rate_ids.sorted("observed_on", reverse=True)[:1]
            if last and last.observed_on and (today - last.observed_on).days < SNAPSHOT_STALE_DAYS:
                continue
            estab.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Saisir les extraits Booking Analytics / Airbnb Insights"),
                note=_(
                    "Phase 1 : recopier le Pace (jusqu'à 10 concurrents) et "
                    "Airbnb Insights. Pas de scraping. Une alerte part si l'écart "
                    "dépasse %s %%."
                )
                % int(estab.pricing_gap_threshold or 10),
            )
            email = estab.pricing_alert_email_resolved()
            if email:
                try:
                    from odoo.addons.doorway_messaging.services.email_service import (
                        EmailService,
                    )

                    EmailService(self.env).send_email(
                        email,
                        _("[%s] Rappel : extraits tarifaires de la semaine")
                        % (estab.name or _("Riad")),
                        _(
                            "<p>Aucune saisie depuis 7 jours. "
                            "Ouvrez Booking Analytics (Pace) et Airbnb Insights, "
                            "puis enregistrez les tarifs dans Module Hébergement "
                            "→ Tarification.</p>"
                            "<p style='color:#9C9280;font-size:12px'>"
                            "Sources officielles uniquement — zéro scraping. "
                            "Phase 2 (règles internes + pont Channex) est différée.</p>"
                        ),
                        recipient_name=estab.name or "",
                    )
                except Exception:  # noqa: BLE001
                    _logger.exception("Rappel hebdo tarif")
            estab.pricing_last_reminder_on = today
        return True
