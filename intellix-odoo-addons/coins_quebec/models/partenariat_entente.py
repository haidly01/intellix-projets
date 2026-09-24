# -*- coding: utf-8 -*-
import logging
import os
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path

from ..data.clauses_visibilite_quebec import cq_visibilite_clauses_html

_logger = logging.getLogger(__name__)

# coins.entente.type_partenaire n'a pas resto/spa/activité — on mappe.
_CQ_ENTENTE_TYPE = {
    "hebergement": "hebergement",
}
_CQ_COMMISSION = {
    "hebergement": 15.0,
    "spa": 15.0,
    "resto": 10.0,
    "activite": 10.0,
    "evenement": 10.0,
    "traiteur": 10.0,
    "fleuriste": 10.0,
    "dj": 10.0,
    "mobilier": 10.0,
    "autre": 10.0,
}
_CQ_CATEGORIE = {
    "hebergement": "Hébergement",
    "spa": "Spa / bien-être",
    "resto": "Restaurant / Gourmand",
    "activite": "Activité / divertissement",
    "evenement": "Événement",
    "traiteur": "Traiteur",
    "fleuriste": "Fleuriste",
    "dj": "DJ / animation",
    "mobilier": "Location mobilier",
    "autre": "Partenaire",
}


class CoinsQuebecPartenariatEntente(models.Model):
    _inherit = "coins.quebec.partenariat"

    cq_entente_res_id = fields.Integer(
        string="Entente (id)",
        copy=False,
        index=True,
    )
    cq_entente_label = fields.Char(
        string="Entente",
        compute="_compute_cq_entente_label",
    )
    cq_entente_html_url = fields.Char(
        string="URL de l'entente (HTML)",
        copy=False,
        help="Lien public du devis/entente. Utilisé par le courrier de bonjour. "
        "Exemple : https://coinsquebec.com/prive/entente-diamant-de-lune.html",
    )

    def _cq_entente_model(self):
        if "coins.entente" not in self.env:
            raise UserError(
                _("Le module d'ententes n'est pas installé sur cette base.")
            )
        return self.env["coins.entente"].sudo()

    def _cq_commission_pct(self):
        self.ensure_one()
        return _CQ_COMMISSION.get(self.type_partenaire or "autre", 10.0)

    def _cq_entente_clauses_html(self):
        self.ensure_one()
        kind = self.type_partenaire or "autre"
        if kind == "hebergement":
            return False
        return cq_visibilite_clauses_html(
            _CQ_CATEGORIE.get(kind, "Partenaire"),
            self._cq_commission_pct(),
        )

    def _cq_browse_entente(self):
        self.ensure_one()
        if "coins.entente" not in self.env or not self.cq_entente_res_id:
            return self.env["coins.entente"].browse() if "coins.entente" in self.env else False
        rec = self.env["coins.entente"].sudo().browse(self.cq_entente_res_id)
        return rec if rec.exists() else rec.browse()

    @api.depends("cq_entente_res_id")
    def _compute_cq_entente_label(self):
        for rec in self:
            entente = rec._cq_browse_entente() if rec.cq_entente_res_id else False
            if not entente:
                rec.cq_entente_label = _("Aucune entente")
            elif entente.date_signature:
                rec.cq_entente_label = _("Signée")
            else:
                rec.cq_entente_label = _("À signer")

    def _cq_ensure_entente(self):
        """Crée ou met à jour l'entente liée à cette fiche (resto compris)."""
        self.ensure_one()
        Entente = self._cq_entente_model()
        partner = self._ensure_partner() if hasattr(self, "_ensure_partner") else self.partner_id
        contact = (self.email or "").strip() or (self.phone or "").strip()
        pct = self._cq_commission_pct()
        kind = self.type_partenaire or "autre"
        categorie = _CQ_CATEGORIE.get(kind, "Partenaire")
        notes = "Coins Québec CAD — %s · %s %%" % (categorie, int(pct))
        vals = {
            "type_partenaire": _CQ_ENTENTE_TYPE.get(kind, "autre"),
            "partenaire_nom": (self.contact_name or "").strip() or (self.name or ""),
            "etablissement": self.name or "",
            "contact_partenaire": contact,
            "pourcentage_commission": pct,
            "type_remuneration": "commission",
            "duree_cycle": "1_mois",
            "shooting_souhaite": True,
            "partner_id": partner.id if partner else False,
            "notes": notes,
            "statut_entente": "en_attente_signature",
        }
        clauses = self._cq_entente_clauses_html()
        if clauses:
            vals["clauses_html"] = clauses
        entente = self._cq_browse_entente()
        if entente:
            if not entente.date_signature:
                entente.write(vals)
        else:
            entente = Entente.create(vals)
            self.sudo().write({"cq_entente_res_id": entente.id})
        return entente

    def action_open_cq_entente(self):
        self.ensure_one()
        entente = self._cq_browse_entente()
        if not entente:
            return self.action_send_cq_entente()
        return {
            "type": "ir.actions.act_window",
            "name": _("Entente"),
            "res_model": "coins.entente",
            "res_id": entente.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_send_cq_entente(self):
        """Ouvre le wizard mauve — l'envoi est confirmé dans le popup."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer l'entente"),
            "res_model": "coins.quebec.send.entente.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partenariat_id": self.id},
        }

    def _cq_pre_entente_offer_block(self):
        """Bloc HTML d'explication — visibilité ou Channel Manager."""
        self.ensure_one()
        kind = self.type_partenaire or "autre"
        pct = int(self._cq_commission_pct())
        if kind == "hebergement":
            return (
                '<h2 style="font-size:18px;color:#1F2A1E;margin:0 0 10px;">'
                "Ce que Coins Québec vous propose</h2>"
                '<p style="margin:0 0 12px;">Fiche voyageur, Channel Manager '
                "(Booking.com / Airbnb) et shooting photo/vidéo — émis par "
                "<strong>Agence Doorway</strong>.</p>"
                "<ul style=\"margin:0 0 16px 18px;padding:0;\">"
                "<li style=\"margin:0 0 8px;\"><strong>Le Channel Manager est "
                "inclus, sans abonnement.</strong> Disponibilités et tarifs à jour "
                "partout, sans double réservation.</li>"
                "<li style=\"margin:0 0 8px;\"><strong>On ne demande jamais votre "
                "mot de passe</strong> Booking ou Airbnb — autorisation officielle "
                "uniquement.</li>"
                "<li style=\"margin:0 0 8px;\">Commission : <strong>10&nbsp;%</strong> "
                "en plus sur une plateforme connectée, <strong>15&nbsp;%</strong> "
                "en direct via Coins Québec. Aucun frais un mois sans réservation.</li>"
                "<li style=\"margin:0;\">Devis et factures en <strong>$ CAD</strong> "
                "(TPS/TVQ). Paiement par <strong>virement Interac</strong> à "
                "<strong>comptabilite@agencedoorway.com</strong>.</li>"
                "</ul>"
            )
        return (
            '<h2 style="font-size:18px;color:#1F2A1E;margin:0 0 10px;">'
            "Ce que Coins Québec vous propose</h2>"
            '<p style="margin:0 0 12px;">Votre établissement sur la carte '
            "Coins Québec — émis par "
            "<strong>Agence Doorway</strong>.</p>"
            "<ul style=\"margin:0 0 16px 18px;padding:0;\">"
            "<li style=\"margin:0 0 8px;\"><strong>Fiche + visibilité</strong>, "
            "sans abonnement fixe.</li>"
            "<li style=\"margin:0 0 8px;\">Le shooting photo/vidéo n'est "
            "<strong>pas inclus</strong> — disponible en option avec "
            "l'Agence Doorway (volet marketing).</li>"
            "<li style=\"margin:0 0 8px;\">Commission de <strong>%s&nbsp;%%</strong> "
            "seulement sur ce qui est réellement apporté. Aucun frais un mois "
            "sans apport Coins Québec.</li>"
            "<li style=\"margin:0;\">Devis et factures en <strong>$ CAD</strong> "
            "(TPS/TVQ). Paiement par <strong>virement Interac</strong> à "
            "<strong>comptabilite@agencedoorway.com</strong>.</li>"
            "</ul>"
        ) % pct

    def _cq_render_pre_entente_html(self):
        """Email d'explication (marque CQ) envoyé juste avant le lien de signature."""
        self.ensure_one()
        path = os.path.join(
            get_module_path("coins_quebec"),
            "data",
            "emails",
            "email_avant_entente.html",
        )
        if not os.path.isfile(path):
            raise UserError(_("Fichier HTML avant-entente introuvable."))
        html = open(path, encoding="utf-8").read()
        contact = ((self.contact_name or "").strip().split() or [""])[0] or "Madame, Monsieur"
        etab = (self.name or "").strip() or "votre établissement"
        ville = (self.city or "").strip() or "votre ville"
        categorie = _CQ_CATEGORIE.get(self.type_partenaire or "autre", "Partenaire")
        sender = (self.env.user.name or "").strip() or "Martin Houle"
        video_href, video_img = ("", "")
        if hasattr(self, "_cq_followup_video_urls"):
            video_href, video_img = self._cq_followup_video_urls()
        html = html.replace("{{CONTACT}}", str(escape(contact)))
        html = html.replace("{{ETABLISSEMENT}}", str(escape(etab)))
        html = html.replace("{{VILLE}}", str(escape(ville)))
        html = html.replace("{{CATEGORIE}}", str(escape(categorie)))
        html = html.replace("{{VIDEO_HREF}}", str(escape(video_href)))
        html = html.replace("{{VIDEO_IMG}}", str(escape(video_img)))
        html = html.replace("{{SENDER}}", str(escape(sender)))
        html = html.replace("{{OFFER_BLOCK}}", self._cq_pre_entente_offer_block())
        return html

    def _cq_send_pre_entente_email(self):
        """Courriel d'explication Agence Doorway — avant le lien OTP."""
        self.ensure_one()
        email = (self.email or "").strip()
        if not email and self.partner_id:
            email = (self.partner_id.email or "").strip()
        if not email:
            return False
        try:
            body = self._cq_render_pre_entente_html()
        except (OSError, UserError) as exc:
            _logger.warning("CQ pre-entente HTML fail: %s", exc)
            return False
        sender = (
            (self.env.user.email_formatted or "").strip()
            or "Martin Houle <martin@agencedoorway.com>"
        )
        mail = self.env["mail.mail"].sudo().create(
            {
                "email_to": email,
                "email_from": sender,
                "subject": _("Coins Québec — avant l'entente · %s")
                % (self.name or "votre établissement"),
                "body_html": body,
            }
        )
        mail.send()
        self.message_post(
            body=_("Email d'explication (Agence Doorway) envoyé à %s, avant l'entente.")
            % email
        )
        return True

    def action_cq_send_entente_now(self):
        """Crée l'entente (10 % resto / activité, 15 % hôtel / spa) et l'envoie."""
        self.ensure_one()
        entente = self._cq_ensure_entente()
        if self.stage not in ("gagne", "perdu", "entente"):
            self.sudo().write({"stage": "entente"})
        if entente.date_signature:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Entente déjà signée"),
                    "message": _("%s — ouvrez l'entente pour le PDF.") % self.name,
                    "type": "success",
                    "sticky": False,
                    "next": self.action_open_cq_entente(),
                },
            }
        contact = (self.email or "").strip() or (self.phone or "").strip()
        if not contact and entente.partner_id:
            contact = (
                (entente.partner_id.email or "").strip()
                or (entente.partner_id.phone or "").strip()
                or (getattr(entente.partner_id, "mobile", None) or "")
            ).strip()
        if not contact:
            self.message_post(
                body=_(
                    "Entente créée pour %s. Ajoutez l'email ou le téléphone "
                    "puis cliquez de nouveau sur Envoyer l'entente."
                )
                % (self.name or "")
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Entente prête"),
                    "message": _(
                        "Ajoutez l'email ou le téléphone du contact, "
                        "puis renvoyez. L'entente n'est pas encore partie."
                    ),
                    "type": "warning",
                    "sticky": True,
                    "next": self.action_open_cq_entente(),
                },
            }
        if not (entente.contact_partenaire or "").strip():
            entente.write({"contact_partenaire": contact})
        try:
            self._cq_send_pre_entente_email()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("CQ pre-entente send fail: %s", exc)
        send = getattr(entente, "action_envoyer_signature", None)
        if not callable(send):
            raise UserError(_("Envoi de signature indisponible sur cette base."))
        send()
        sig = entente.signature_id
        if sig and "document_name" in sig._fields:
            sig.sudo().write(
                {
                    "document_name": _("Entente visibilité Coins Québec — %s")
                    % (self.name or entente.etablissement or "")
                }
            )
        self.message_post(
            body=_("Entente visibilité envoyée à %s (%s %% — %s).")
            % (
                contact,
                int(self._cq_commission_pct()),
                _CQ_CATEGORIE.get(self.type_partenaire or "autre", "Partenaire"),
            )
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Entente envoyée"),
                "message": _(
                    "Le partenaire peut signer. Commission %s %% — %s."
                )
                % (
                    int(self._cq_commission_pct()),
                    _CQ_CATEGORIE.get(self.type_partenaire or "autre", ""),
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def _cq_intro_contact_firstname(self):
        self.ensure_one()
        first = (getattr(self, "contact_firstname", None) or "").strip()
        if first:
            return first
        return ((self.contact_name or "").strip().split() or [""])[0] or "Madame, Monsieur"

    def _cq_entente_public_url(self):
        """Lien du devis/entente — jamais une pièce jointe."""
        self.ensure_one()
        explicit = (self.cq_entente_html_url or "").strip()
        if explicit:
            return explicit
        name = (self.name or "").strip().lower()
        if "diamant" in name and "lune" in name:
            return "https://coinsquebec.com/prive/entente-diamant-de-lune.html"
        slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "partenaire"
        return "https://coinsquebec.com/prive/entente-%s.html" % slug

    def _cq_intro_pillar_html(self, title, body, last=False):
        margin = "0" if last else "0 0 16px"
        return (
            '<div style="margin:%s;">'
            '<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
            'font-weight:600;font-size:16.5px;color:#1F2A1E;">%s</div>'
            '<div style="font-size:13px;color:#4C5645;line-height:1.6;margin-top:4px;">%s</div>'
            "</div>"
        ) % (margin, title, body)

    def _cq_intro_offer_blocks(self):
        """Trois volets — digitalisation honnête selon le type (hôtel ≠ boutique)."""
        self.ensure_one()
        kind = self.type_partenaire or "autre"
        pct = int(self._cq_commission_pct())
        if kind == "hebergement":
            visib = (
                "Présence sur la carte Coins Québec et le réseau. "
                "Commission de <strong>%s&nbsp;%%</strong> uniquement sur ce qui "
                "est réellement généré via Coins Québec "
                "(<strong>10&nbsp;%%</strong> en plus sur une plateforme connectée). "
                "Aucun frais un mois sans réservation."
            ) % pct
            digital = (
                "Module de gestion des réservations (Channel Manager), "
                "connecté à plus de 200 plateformes — Booking, Airbnb et le reste, "
                "sans double réservation. Optionnel."
            )
        elif kind == "spa":
            visib = (
                "Présence sur la carte Coins Québec et le réseau. "
                "Commission de <strong>%s&nbsp;%%</strong> uniquement sur ce qui "
                "est réellement généré — aucun frais fixe."
            ) % pct
            digital = (
                "Prise de rendez-vous en ligne pour les soins, présence et "
                "disponibilités. Optionnel — "
                "<strong>10&nbsp;% des réservations ou 199&nbsp;$ CAD/mois</strong>."
            )
        elif kind == "resto":
            visib = (
                "Présence sur la carte Coins Québec et le réseau. "
                "Commission de <strong>%s&nbsp;%%</strong> uniquement sur ce qui "
                "est réellement généré — aucun frais fixe."
            ) % pct
            digital = (
                "Gestion des réservations en ligne et présence. Optionnel — "
                "<strong>10&nbsp;% des réservations ou 199&nbsp;$ CAD/mois</strong>."
            )
        elif kind == "activite":
            visib = (
                "Présence sur la carte Coins Québec et le réseau. "
                "Commission de <strong>%s&nbsp;%%</strong> uniquement sur ce qui "
                "est réellement généré — aucun frais fixe."
            ) % pct
            digital = (
                "Calendrier de disponibilités et réservations directes, "
                "raccordable à votre site. Optionnel."
            )
        else:
            visib = (
                "Présence sur la carte Coins Québec et le réseau. "
                "Commission de <strong>%s&nbsp;%%</strong> uniquement sur ce qui "
                "est réellement généré — aucun frais fixe."
            ) % pct
            digital = (
                "Présence en ligne et prise de rendez-vous pour les soins, "
                "consultations ou visites. Sans abonnement fixe."
            )
        marketing = (
            "Site web, présence réseaux sociaux et contenu photo/vidéo avec "
            "l'Agence Doorway — seulement si vous voulez pousser plus loin."
        )
        return {
            "visibility": self._cq_intro_pillar_html(
                "Visibilité Coins Québec", visib
            ),
            "digital": self._cq_intro_pillar_html(
                "Digitalisation (optionnel)", digital
            ),
            "marketing": self._cq_intro_pillar_html(
                "Marketing (optionnel)", marketing, last=True
            ),
        }

    def _cq_intro_html_path(self):
        path = os.path.join(
            get_module_path("coins_quebec"),
            "data",
            "emails",
            "email_introduction_entente.html",
        )
        if not os.path.isfile(path):
            raise UserError(_("Fichier HTML d'introduction d'entente introuvable."))
        return path

    def _cq_render_intro_entente_html(self):
        """Courrier de bonjour — présentation de l'entente (modèle réutilisable)."""
        self.ensure_one()
        html = open(self._cq_intro_html_path(), encoding="utf-8").read()
        contact = self._cq_intro_contact_firstname()
        etab = (self.name or "").strip() or "votre établissement"
        sender = (self.env.user.name or "").strip() or "Martin Houle"
        blocks = self._cq_intro_offer_blocks()
        html = html.replace("{{CONTACT}}", str(escape(contact)))
        html = html.replace("{{ETABLISSEMENT}}", str(escape(etab)))
        html = html.replace("{{SENDER}}", str(escape(sender)))
        html = html.replace("{{ENTENTE_URL}}", str(escape(self._cq_entente_public_url())))
        html = html.replace("{{VISIBILITY_BLOCK}}", blocks["visibility"])
        html = html.replace("{{DIGITAL_BLOCK}}", blocks["digital"])
        html = html.replace("{{MARKETING_BLOCK}}", blocks["marketing"])
        return html

    def _cq_intro_subject(self):
        self.ensure_one()
        etab = (self.name or "").strip() or "votre établissement"
        return _("Coins Québec × %s — présentation de l'entente de partenariat") % etab

    def action_send_cq_intro_entente(self):
        """Ouvre le compositeur (brouillon) — n'envoie pas automatiquement."""
        self.ensure_one()
        template = self.env.ref(
            "coins_quebec.mail_template_cq_intro_entente",
            raise_if_not_found=False,
        )
        if not template:
            template = self.env["mail.template"].sudo().search(
                [
                    ("model", "=", "coins.quebec.partenariat"),
                    ("name", "ilike", "Introduction 1"),
                ],
                limit=1,
            )
        ctx = {
            "default_model": "coins.quebec.partenariat",
            "default_res_ids": self.ids,
            "default_composition_mode": "comment",
            "mail_post_autofollow": True,
            "active_model": "coins.quebec.partenariat",
            "active_ids": self.ids,
            "active_id": self.id,
        }
        if template:
            ctx.update(
                {
                    "default_template_id": template.id,
                    "default_use_template": True,
                }
            )
        try:
            rendered = self._cq_render_intro_entente_html()
        except (OSError, UserError):
            rendered = ""
        if rendered:
            ctx.update(
                {
                    "default_subject": self._cq_intro_subject(),
                    "default_body": Markup(rendered),
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Courrier de bonjour"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
