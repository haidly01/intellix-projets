# -*- coding: utf-8 -*-
"""Modèle standard hébergement + envoi signature Karine.

Ne modifie pas la validation OTP (people_engine). Ne migre pas Riad Djemanna / S00021.
"""
import logging
import os
from datetime import datetime

from markupsafe import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

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

DJEMANNA_ENTENTE_ID = 15
DJEMANNA_SO_NAME = "S00021"


def _coins_format_date_fr(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    try:
        return "%s %s %s" % (value.day, _MONTHS_FR[value.month - 1], value.year)
    except Exception:  # noqa: BLE001
        return str(value)


class CoinsEntente(models.Model):
    _inherit = "coins.entente"

    def _coins_is_frozen_djemanna(self):
        """Entente S00021 / Riad Djemanna : ancien modèle, ne pas migrer."""
        rec = self[:1]
        if not rec:
            return False
        if rec.id == DJEMANNA_ENTENTE_ID:
            return True
        blob = " ".join(
            [
                rec.etablissement or "",
                rec.partenaire_nom or "",
                rec.name or "",
            ]
        ).lower()
        if "djemanna" in blob:
            return True
        order = self.env["sale.order"].sudo().search(
            [("coins_entente_id", "=", rec.id)], limit=1
        )
        if order and (order.name or "") == DJEMANNA_SO_NAME:
            return True
        html = (rec.clauses_html or "").lower()
        if "taux unique de 15" in html or "commission de coins marocain seule" in html:
            return True
        return False

    def _coins_clauses_are_legacy_hebergement(self, html=None):
        text = html if html is not None else (self.clauses_html or "")
        return "Sans durée minimale" in (text or "")

    def _coins_clauses_are_standard_hebergement(self, html=None):
        text = html if html is not None else (self.clauses_html or "")
        return "data-coins-modele=\"hebergement-standard-2026\"" in (text or "") or (
            "jamais les deux barèmes cumulés" in (text or "")
        )

    def _coins_clauses_are_visibilite_cm(self, html=None):
        text = html if html is not None else (self.clauses_html or "")
        return 'data-coins-modele="visibilite-cm-2026"' in (text or "")

    def _coins_related_quote(self):
        rec = self[:1]
        if not rec:
            return self.env["sale.order"]
        order = self.env["sale.order"].sudo().search(
            [("coins_entente_id", "=", rec.id)], limit=1
        )
        if order:
            return order
        lead = rec._coins_related_crm_lead() if hasattr(rec, "_coins_related_crm_lead") else False
        if lead and lead.coins_sale_order_id:
            return lead.coins_sale_order_id
        return self.env["sale.order"]

    def _coins_should_use_visibilite_clauses(self):
        """Défaut CM : visibilité 15 % seule. Digitalisation / Channex gardent le pack hébergement."""
        self.ensure_one()
        if self._coins_is_frozen_djemanna() or self._coins_is_quebec_entente():
            return False
        if self.type_partenaire != "hebergement":
            return False
        if self._coins_clauses_are_visibilite_cm():
            return True
        if self._coins_clauses_are_standard_hebergement():
            return False
        order = self._coins_related_quote()
        if order and hasattr(order, "_coins_quote_is_visibilite_only"):
            return bool(order._coins_quote_is_visibilite_only())
        lead = self._coins_related_crm_lead() if hasattr(self, "_coins_related_crm_lead") else False
        if lead and getattr(lead, "coins_interet_channel_manager", False):
            return False
        tmpl_code = ""
        if order:
            tmpl_code = getattr(order, "ix_template_code", "") or ""
            if order.sale_order_template_id:
                tmpl_code = tmpl_code or (
                    getattr(order.sale_order_template_id, "ix_template_code", "") or ""
                )
        if tmpl_code in ("coins_digitalisation", "coins_presence_complete"):
            return False
        return True

    def _coins_should_refresh_standard_clauses(self):
        self.ensure_one()
        if self._coins_is_frozen_djemanna() or self.date_signature:
            return False
        if self.type_partenaire != "hebergement":
            return False
        if self._coins_is_quebec_entente():
            return False
        html = self.clauses_html or ""
        if self._coins_clauses_are_visibilite_cm(html):
            return False
        if not html.strip():
            return True
        if self._coins_clauses_are_legacy_hebergement(html):
            return True
        return False

    @api.model
    def _coins_load_standard_hebergement_template(self):
        path = os.path.join(
            get_module_path("coins_marocain_partenariats"),
            "data",
            "clauses_hebergement_standard.html",
        )
        if not os.path.isfile(path):
            from ..data.clauses_hebergement import CLAUSES_HEBERGEMENT_HTML

            return CLAUSES_HEBERGEMENT_HTML
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def _coins_placeholder_context(self, vals=None):
        vals = vals or {}
        rec = self[:1]
        partner = rec.partner_id if rec else self.env["res.partner"]

        def _val(*keys):
            for key in keys:
                raw = vals.get(key)
                if raw:
                    return str(raw).strip()
            return ""

        etablissement = (
            _val("etablissement")
            or (rec.etablissement if rec else "")
            or _val("partenaire_nom")
            or (rec.partenaire_nom if rec else "")
            or (partner.name if partner else "")
            or (rec.name if rec else "")
            or "l'établissement"
        )
        contact = (
            _val("partenaire_nom")
            or (rec.partenaire_nom if rec else "")
            or (partner.name if partner else "")
            or etablissement
        )
        email = (
            _val("contact_partenaire")
            or (rec.contact_partenaire if rec else "")
            or (partner.email if partner else "")
            or ""
        )
        if email and "@" not in email:
            email = (partner.email if partner else "") or email
        phone = ""
        if partner:
            phone = (partner.phone or getattr(partner, "mobile", False) or "") or ""
        if rec and not phone:
            extra = rec.contact_partenaire or ""
            if extra and "@" not in extra:
                phone = extra
        street_bits = []
        if partner:
            country = partner.country_id.name if partner.country_id else ""
            for bit in (
                partner.street,
                getattr(partner, "street2", False) or "",
                partner.city,
                partner.zip,
                country,
            ):
                if bit:
                    street_bits.append(bit)
        adresse = ", ".join(street_bits)
        today = fields.Date.context_today(self)
        date_txt = _coins_format_date_fr(today)
        phone_line = ("<br/>Tél. : %s" % escape(phone)) if phone else ""
        adresse_block = ("%s<br/>" % escape(adresse)) if adresse else ""
        return {
            "PARTENAIRE": etablissement,
            "CONTACT": contact,
            "EMAIL": email or "—",
            "DATE": date_txt,
            "CATEGORIE": "Hébergement",
            "PHONE_LINE": phone_line,
            "ADRESSE_BLOCK": adresse_block,
        }

    def _coins_fill_placeholders(self, html, vals=None):
        ctx = self._coins_placeholder_context(vals)
        for key, value in ctx.items():
            token = "{{%s}}" % key
            if key in ("PHONE_LINE", "ADRESSE_BLOCK"):
                html = html.replace(token, value)
            else:
                html = html.replace(token, str(escape(value)))
        return html

    def _coins_render_standard_hebergement(self, vals=None):
        return self._coins_fill_placeholders(
            self._coins_load_standard_hebergement_template(), vals
        )

    @api.model
    def _coins_load_visibilite_cm_template(self):
        path = os.path.join(
            get_module_path("coins_marocain_partenariats"),
            "data",
            "clauses_visibilite_cm.html",
        )
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def _coins_render_visibilite_cm(self, vals=None):
        return self._coins_fill_placeholders(
            self._coins_load_visibilite_cm_template(), vals
        )

    @api.model
    def _coins_default_clauses_html_from_vals(self, vals):
        vals = vals or {}
        if self._coins_is_quebec_entente(vals):
            return super()._coins_default_clauses_html_from_vals(vals)
        if vals.get("type_partenaire") == "hebergement":
            return self._coins_render_visibilite_cm(vals)
        return super()._coins_default_clauses_html_from_vals(vals)

    def _coins_default_clauses_html(self):
        if (
            self
            and self.type_partenaire == "hebergement"
            and not self._coins_is_quebec_entente()
            and not self._coins_is_frozen_djemanna()
        ):
            if self._coins_should_use_visibilite_clauses():
                return self._coins_render_visibilite_cm()
            return self._coins_render_standard_hebergement()
        return super()._coins_default_clauses_html()

    def _get_signature_html(self):
        self.ensure_one()
        if self._coins_is_frozen_djemanna() or self._coins_is_quebec_entente():
            return super()._get_signature_html()
        html = self.clauses_html or ""
        if "{{" in html:
            html = self._coins_fill_placeholders(html)
        if self._coins_clauses_are_standard_hebergement(html):
            inner = self._strip_clauses_internes(html)
            offer = ""
            if hasattr(self, "_coins_devis_offer_html"):
                offer = self._coins_devis_offer_html() or ""
            if offer and "data-coins-devis-offer" not in (inner or ""):
                return offer + inner
            return inner
        return super()._get_signature_html()

    def _coins_prepare_signature(self):
        self.ensure_one()
        if (
            not self._coins_is_frozen_djemanna()
            and self.type_partenaire == "hebergement"
            and not self.date_signature
            and not self._coins_is_quebec_entente()
        ):
            if self._coins_should_use_visibilite_clauses():
                html = self.clauses_html or ""
                if not html.strip() or "{{" in html:
                    self.clauses_html = self._coins_render_visibilite_cm()
            elif self._coins_should_refresh_standard_clauses():
                self.clauses_html = self._coins_render_standard_hebergement()
            elif self.clauses_html and "{{" in (self.clauses_html or ""):
                self.clauses_html = self._coins_fill_placeholders(self.clauses_html)
            # Ancien token déjà signé / expiré : en recréer un, sinon /sign/contract dit « expiré ».
            sig = self.signature_id
            if sig and sig.state in ("signed", "expired", "refused"):
                self.write({"signature_id": False, "token_signature": False})
        sig = super()._coins_prepare_signature()
        if (
            sig
            and self._coins_should_use_visibilite_clauses()
            and "Channel Manager" in (sig.document_name or "")
        ):
            sig.sudo().write(
                {
                    "document_name": _(
                        "Entente visibilité Coins Marocain — %s"
                    )
                    % (self.etablissement or self.partenaire_nom or self.name),
                }
            )
        return sig

    def _coins_karine_user(self):
        return self.env["res.users"].sudo().search(
            [("login", "=", "karine@agencedoorway.com")], limit=1
        )

    def _coins_karine_outgoing(self):
        server = (
            self.env["ir.mail_server"]
            .sudo()
            .search([("from_filter", "=", "karine@agencedoorway.com")], limit=1)
        )
        if not server:
            server = self.env["ir.mail_server"].sudo().search(
                [("name", "ilike", "karine")], limit=1
            )
        return {
            "email_from": "Karine Barmaki — Coins Marocain <karine@agencedoorway.com>",
            "mail_server_id": server.id if server else False,
        }

    def _coins_signature_email_html(self, sign_url):
        self.ensure_one()
        path = os.path.join(
            get_module_path("coins_marocain_partenariats"),
            "data",
            "emails",
            "email_signature_karine.html",
        )
        html = open(path, encoding="utf-8").read()
        etab = self.etablissement or self.partenaire_nom or self.name or "votre établissement"
        html = html.replace("{{ETABLISSEMENT}}", str(escape(etab)))
        html = html.replace("{{SIGN_URL}}", str(escape(sign_url or "")))
        return html

    def _coins_envoyer_signature_karine(self):
        """Génère le token /sign/contract/<token> et envoie l'email Karine — sans WhatsApp."""
        self.ensure_one()
        if self.date_signature:
            raise UserError(_("Cette entente est déjà signée."))
        if self.type_partenaire != "hebergement":
            raise UserError(
                _("Le modèle standard ne s'applique qu'aux partenaires Hébergement.")
            )
        if self._coins_is_frozen_djemanna():
            raise UserError(
                _(
                    "L'entente Riad Djemanna (S00021) reste sur son modèle d'origine "
                    "et n'est pas renvoyée via le flux standard."
                )
            )
        email = self._signer_email()
        if not email:
            raise UserError(
                _("Renseignez l'email du partenaire avant d'envoyer pour signature.")
            )
        sig = self._coins_prepare_signature()
        if sig.signer_phone:
            sig.sudo().write({"signer_phone": False})
        sign_url = sig.get_sign_url()
        outgoing = self._coins_karine_outgoing()
        mail_vals = {
            "email_to": email,
            "email_from": outgoing["email_from"],
            "subject": _("Bienvenue chez Coins Marocain — votre entente de partenariat"),
            "body_html": self._coins_signature_email_html(sign_url),
            "auto_delete": False,
        }
        if outgoing.get("mail_server_id"):
            mail_vals["mail_server_id"] = outgoing["mail_server_id"]
        mail = self.env["mail.mail"].sudo().create(mail_vals)
        mail.send()
        if sig.state == "pending":
            sig.sudo().write({"state": "otp_sent"})
        self.write({"date_envoi_signature": fields.Datetime.now()})
        self.message_post(
            body=_(
                "Entente standard hébergement envoyée pour signature à %s<br/>"
                "Lien : <a href=\"%s\">%s</a>"
            )
            % (email, sign_url, sign_url)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Envoyé pour signature"),
                "message": _("Email envoyé à %s") % email,
                "type": "success",
                "sticky": False,
            },
        }

    def action_envoyer_signature(self):
        self.ensure_one()
        if (
            self.type_partenaire == "hebergement"
            and not self._coins_is_quebec_entente()
            and not self._coins_is_frozen_djemanna()
        ):
            return self._coins_envoyer_signature_karine()
        return super().action_envoyer_signature()

    def _coins_notify_karine_signed(self):
        self.ensure_one()
        etab = self.etablissement or self.partenaire_nom or self.name
        signed = self.date_signature or fields.Datetime.now()
        date_txt = _coins_format_date_fr(signed)
        if isinstance(signed, datetime):
            heure = signed.strftime("%H:%M")
            date_txt = "%s à %s" % (date_txt, heure)
        body = _(
            "<p><strong>%s</strong> a signé l'entente de partenariat "
            "le %s.</p>"
        ) % (escape(etab), escape(date_txt))
        karine = self._coins_karine_user()
        outgoing = self._coins_karine_outgoing()
        mail_vals = {
            "email_to": "karine@agencedoorway.com",
            "email_from": outgoing["email_from"],
            "subject": _("Entente signée — %s") % etab,
            "body_html": (
                '<div style="font-family:Georgia,serif;color:#3A2E1F;">%s'
                "<p>Coins Marocain</p></div>"
            )
            % body,
            "auto_delete": False,
        }
        if outgoing.get("mail_server_id"):
            mail_vals["mail_server_id"] = outgoing["mail_server_id"]
        self.env["mail.mail"].sudo().create(mail_vals).send()
        self.message_post(
            body=_("Notification Karine : %s a signé le %s.") % (etab, date_txt),
            partner_ids=karine.partner_id.ids if karine else [],
            subtype_xmlid="mail.mt_note",
        )
        if karine:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=karine.id,
                summary=_("Entente signée — %s") % etab,
                note=_("Le partenaire a validé l'OTP le %s.") % date_txt,
            )

    def _on_electronic_signed(self, signature):
        res = None
        try:
            res = super()._on_electronic_signed(signature)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("post-signature (super) : %s", exc)
            self.message_post(
                body=_("Signature enregistrée, mais une étape automatique a échoué : %s")
                % exc
            )
        try:
            if not self.date_signature:
                self.write(
                    {
                        "statut_entente": "active",
                        "date_signature": fields.Datetime.now(),
                    }
                )
            self._coins_notify_karine_signed()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("notif Karine post-signature: %s", exc)
            self.message_post(
                body=_("Signature OK, mais la notification Karine a échoué : %s") % exc
            )
        return res
