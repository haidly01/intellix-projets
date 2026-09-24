# -*- coding: utf-8 -*-
import base64
import logging
import re
import secrets
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..data.clauses_hebergement import CLAUSES_HEBERGEMENT_HTML
from ..data.clauses_hebergement_quebec import CLAUSES_HEBERGEMENT_QUEBEC_HTML

_logger = logging.getLogger(__name__)


class CoinsEntente(models.Model):
    _name = "coins.entente"
    _description = "Entente / partenariat Coins Marocain"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_debut desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default="Nouveau",
        tracking=True,
    )
    type_partenaire = fields.Selection(
        [
            ("influenceur", "Influenceur"),
            ("wedding_planner", "Wedding planner"),
            ("agence_voyage", "Agence de voyage"),
            ("organisateur_congres", "Organisateur congrès"),
            ("hebergement", "Hôtel / Riad / Villa"),
            ("autre", "Autre"),
        ],
        string="Type de partenaire",
        required=True,
        default="influenceur",
        tracking=True,
        index=True,
    )
    influenceur_id = fields.Many2one(
        "coins.influenceur",
        string="Influenceur",
        ondelete="set null",
        tracking=True,
        index=True,
    )
    partenaire_nom = fields.Char(
        string="Nom partenaire B2B",
        help="Pour les partenaires sans fiche influenceur.",
        tracking=True,
    )
    contact_partenaire = fields.Char(
        string="Contact partenaire",
        help="Email ou téléphone WhatsApp (partenaires B2B).",
        tracking=True,
    )
    etablissement = fields.Char(
        string="Établissement",
        help="Restaurant, riad, spa ou lieu concerné.",
        tracking=True,
    )
    type_remuneration = fields.Selection(
        [
            ("experience", "Expérience offerte"),
            ("commission", "Commission"),
            ("experience_commission", "Expérience + commission"),
            ("forfait", "Forfait fixe"),
        ],
        string="Type de rémunération",
        default="experience_commission",
        tracking=True,
    )
    pourcentage_commission = fields.Float(
        string="Commission (%)",
        digits=(16, 2),
        tracking=True,
    )
    part_doorway = fields.Monetary(
        string="Part Doorway",
        currency_field="currency_id",
        help="Montant conservé par Doorway sur la commission du cycle.",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    duree_cycle = fields.Selection(
        [
            ("1_mois", "1 mois"),
            ("3_mois", "3 mois"),
            ("autre", "Autre"),
        ],
        string="Durée du cycle",
        default="3_mois",
        required=True,
        tracking=True,
    )
    date_debut = fields.Date(
        string="Date de début",
        default=fields.Date.context_today,
        tracking=True,
    )
    date_renouvellement = fields.Date(
        string="Date de renouvellement",
        tracking=True,
        help="Calculée automatiquement pour 1 mois / 3 mois ; saisie libre si Autre.",
    )
    statut_entente = fields.Selection(
        [
            ("en_attente_signature", "En attente de signature"),
            ("active", "Active"),
            ("a_renouveler", "À renouveler"),
            ("terminee", "Terminée"),
            ("declinee", "Déclinée"),
        ],
        string="Statut",
        default="active",
        required=True,
        tracking=True,
        index=True,
    )
    code_promo = fields.Char(
        string="Code promo",
        index=True,
        tracking=True,
        copy=False,
    )
    lien_activation = fields.Char(
        string="Lien d'activation",
        copy=False,
        tracking=True,
        help="URL unique de suivi (réservation / commande personnalisée).",
    )
    date_activation = fields.Date(
        string="Première activation",
        readonly=True,
        copy=False,
    )
    nombre_activations = fields.Integer(
        string="Nombre d'activations",
        compute="_compute_activation_stats",
        store=True,
    )
    montant_ventes_generees = fields.Monetary(
        string="Ventes générées",
        currency_field="currency_id",
        compute="_compute_activation_stats",
        store=True,
        help="Total des ventes trackées via le lien/code sur le cycle (somme des activations).",
    )
    commission_calculee = fields.Monetary(
        string="Commission calculée",
        currency_field="currency_id",
        compute="_compute_commission",
        store=True,
    )
    part_influenceur_calculee = fields.Monetary(
        string="Part partenaire calculée",
        currency_field="currency_id",
        compute="_compute_commission",
        store=True,
        help="commission_calculee − part_doorway",
    )
    date_envoi_lien = fields.Datetime(
        string="Dernier envoi du lien",
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string="Notes")
    partner_id = fields.Many2one(
        "res.partner",
        string="Fiche contact",
        tracking=True,
        help="Contact portail IntelliX du partenaire hébergement.",
    )
    shooting_souhaite = fields.Boolean(
        string="Shooting photo/vidéo à planifier",
        default=True,
        tracking=True,
    )
    clauses_html = fields.Html(
        string="Clauses d'entente",
        sanitize=False,
        help="Texte présenté au partenaire pour signature. Sans avertissement interne.",
    )
    signature_id = fields.Many2one(
        "pe.electronic.signature",
        string="Demande de signature",
        copy=False,
        ondelete="set null",
    )
    token_signature = fields.Char(string="Token signature", copy=False, index=True)
    date_envoi_signature = fields.Datetime(
        string="Envoi signature",
        readonly=True,
        copy=False,
    )
    date_signature = fields.Datetime(
        string="Date de signature",
        readonly=True,
        copy=False,
        tracking=True,
    )
    pdf_signe = fields.Binary(string="Document signé", copy=False)
    pdf_signe_filename = fields.Char(string="Nom fichier signé", copy=False)
    activation_ids = fields.One2many(
        "coins.entente.activation",
        "entente_id",
        string="Activations",
    )
    activation_count = fields.Integer(
        string="Nb activations",
        compute="_compute_activation_count",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.depends("activation_ids", "activation_ids.montant", "activation_ids.date")
    def _compute_activation_stats(self):
        for rec in self:
            acts = rec.activation_ids
            rec.nombre_activations = len(acts)
            rec.montant_ventes_generees = sum(acts.mapped("montant"))
            dates = acts.mapped("date")
            rec.date_activation = min(dates) if dates else False

    @api.depends("activation_ids")
    def _compute_activation_count(self):
        for rec in self:
            rec.activation_count = len(rec.activation_ids)

    @api.depends("montant_ventes_generees", "pourcentage_commission", "part_doorway")
    def _compute_commission(self):
        for rec in self:
            commission = (rec.montant_ventes_generees or 0.0) * (
                (rec.pourcentage_commission or 0.0) / 100.0
            )
            rec.commission_calculee = commission
            rec.part_influenceur_calculee = commission - (rec.part_doorway or 0.0)

    @api.onchange("date_debut", "duree_cycle")
    def _onchange_cycle_dates(self):
        for rec in self:
            if not rec.date_debut:
                continue
            if rec.duree_cycle == "1_mois":
                rec.date_renouvellement = rec.date_debut + relativedelta(months=1)
            elif rec.duree_cycle == "3_mois":
                rec.date_renouvellement = rec.date_debut + relativedelta(months=3)

    @api.onchange("influenceur_id")
    def _onchange_influenceur_id(self):
        if self.influenceur_id and self.type_partenaire == "influenceur":
            if not self.partenaire_nom:
                self.partenaire_nom = self.influenceur_id.name

    @api.onchange("type_partenaire")
    def _onchange_type_partenaire(self):
        if self.type_partenaire == "hebergement":
            if not self.clauses_html:
                self.clauses_html = self._coins_default_clauses_html()
            if self.statut_entente == "active" and not self.date_signature:
                self.statut_entente = "en_attente_signature"
            if self.type_remuneration != "commission":
                self.type_remuneration = "commission"
            if self.duree_cycle != "1_mois":
                self.duree_cycle = "1_mois"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "coins.entente"
                ) or self._generate_ref()
            if not vals.get("code_promo"):
                vals["code_promo"] = self._generate_code_promo(vals)
            if not vals.get("lien_activation"):
                vals["lien_activation"] = self._build_lien_activation(
                    vals.get("code_promo")
                )
            if vals.get("date_debut") and vals.get("duree_cycle") in (
                "1_mois",
                "3_mois",
            ):
                debut = fields.Date.to_date(vals["date_debut"])
                months = 1 if vals["duree_cycle"] == "1_mois" else 3
                vals.setdefault(
                    "date_renouvellement",
                    debut + relativedelta(months=months),
                )
            if vals.get("type_partenaire") == "hebergement":
                vals.setdefault(
                    "clauses_html",
                    self._coins_default_clauses_html_from_vals(vals),
                )
                vals.setdefault("statut_entente", "en_attente_signature")
                vals.setdefault("type_remuneration", "commission")
                vals.setdefault("duree_cycle", "1_mois")
                vals.setdefault("shooting_souhaite", True)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "date_debut" in vals or "duree_cycle" in vals:
            for rec in self:
                if rec.duree_cycle in ("1_mois", "3_mois") and rec.date_debut:
                    months = 1 if rec.duree_cycle == "1_mois" else 3
                    new_date = rec.date_debut + relativedelta(months=months)
                    if rec.date_renouvellement != new_date:
                        super(CoinsEntente, rec).write(
                            {"date_renouvellement": new_date}
                        )
        return res

    @api.model
    def _generate_ref(self):
        return "ENT-%s" % datetime.utcnow().strftime("%Y%m%d%H%M%S")

    @api.model
    def _generate_code_promo(self, vals=None):
        vals = vals or {}
        base = (vals.get("partenaire_nom") or vals.get("name") or "CM").upper()
        base = re.sub(r"[^A-Z0-9]", "", base)[:8] or "CM"
        return "%s-%s" % (base, secrets.token_hex(2).upper())

    @api.model
    def _build_lien_activation(self, code_promo):
        code = (code_promo or "CM").strip()
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain_partenariats.lien_base_url",
                "https://coinsmarocain.com",
            )
            .rstrip("/")
        )
        return "%s/?promo=%s" % (base, code)

    def action_generer_lien(self):
        for rec in self:
            if not rec.code_promo:
                rec.code_promo = rec._generate_code_promo(
                    {
                        "partenaire_nom": rec.partenaire_nom or (rec.influenceur_id.name if rec.influenceur_id else ""),
                        "name": rec.name,
                    }
                )
            rec.lien_activation = rec._build_lien_activation(rec.code_promo)
        return True

    def _resolve_contact(self):
        self.ensure_one()
        if self.contact_partenaire:
            return self.contact_partenaire.strip()
        if self.influenceur_id and self.influenceur_id.contact:
            return self.influenceur_id.contact.strip()
        return ""

    def _contact_is_email(self, contact):
        return bool(contact) and "@" in contact and " " not in contact.strip()

    def _render_message_body(self):
        self.ensure_one()
        partenaire = (
            self.partenaire_nom
            or (self.influenceur_id.name if self.influenceur_id else "")
            or _("partenaire")
        )
        etablissement = self.etablissement or _("Coins Marocain")
        lien = self.lien_activation or ""
        template = self.env.ref(
            "coins_marocain_partenariats.mail_template_coins_entente_lien",
            raise_if_not_found=False,
        )
        if template:
            # Render body_html with record values
            rendered = template._render_field("body_html", self.ids)[self.id]
            # Strip tags lightly for WhatsApp
            text = re.sub(r"<br\s*/?>", "\n", rendered or "", flags=re.I)
            text = re.sub(r"</p>", "\n", text, flags=re.I)
            text = re.sub(r"<[^>]+>", "", text)
            return (rendered or ""), text.strip()
        html = (
            "<p>Bonjour %s,</p>"
            "<p>Voici votre lien d'activation pour <strong>%s</strong> :</p>"
            "<p><a href=\"%s\">%s</a></p>"
            "<p>Code promo : <strong>%s</strong></p>"
            "<p>À bientôt,<br/>Coins Marocain</p>"
        ) % (
            partenaire,
            etablissement,
            lien,
            lien,
            self.code_promo or "",
        )
        text = (
            "Bonjour %s,\n\n"
            "Voici votre lien d'activation pour %s :\n%s\n\n"
            "Code promo : %s\n\n"
            "À bientôt,\nCoins Marocain"
        ) % (partenaire, etablissement, lien, self.code_promo or "")
        return html, text

    def action_envoyer_lien(self):
        """Envoie lien_activation via doorway_messaging (email ou WhatsApp)."""
        self.ensure_one()
        if not self.lien_activation:
            self.action_generer_lien()
        contact = self._resolve_contact()
        if not contact:
            raise UserError(
                _(
                    "Aucun contact : renseignez le contact de l'influenceur "
                    "ou le champ « Contact partenaire »."
                )
            )
        html_body, text_body = self._render_message_body()
        result = None
        canal = None
        if self._contact_is_email(contact):
            from odoo.addons.doorway_messaging.services.email_service import (
                EmailService,
            )

            partenaire = (
                self.partenaire_nom
                or (self.influenceur_id.name if self.influenceur_id else "")
            )
            subject = _("Votre lien partenaire — %s") % (
                self.etablissement or "Coins Marocain"
            )
            result = EmailService(self.env).send_email(
                contact, subject, html_body, recipient_name=partenaire or ""
            )
            canal = "email"
        else:
            from odoo.addons.doorway_messaging.services.whatsapp_service import (
                WhatsAppService,
            )

            phone = contact
            if phone.lower().startswith("whatsapp:"):
                phone = phone.split(":", 1)[1]
            result = WhatsAppService(self.env).send_whatsapp(
                to_number=phone, body=text_body
            )
            canal = "whatsapp"

        if not result or not result.get("success"):
            err = (result or {}).get("error") or _("échec inconnu")
            raise UserError(_("Envoi %s impossible : %s") % (canal, err))

        self.date_envoi_lien = fields.Datetime.now()
        self.message_post(
            body=_(
                "Lien d'activation envoyé par %s à %s<br/>%s"
            )
            % (canal, contact, self.lien_activation)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lien envoyé"),
                "message": _("Envoyé par %s à %s") % (canal, contact),
                "type": "success",
                "sticky": False,
            },
        }

    def action_enregistrer_activation(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Enregistrer une activation"),
            "res_model": "coins.entente.activation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_entente_id": self.id,
                "default_currency_id": self.currency_id.id,
            },
        }

    def action_open_activations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Activations"),
            "res_model": "coins.entente.activation",
            "view_mode": "list,form",
            "domain": [("entente_id", "=", self.id)],
            "context": {"default_entente_id": self.id},
        }

    def _signer_email(self):
        self.ensure_one()
        contact = self._resolve_contact()
        if self._contact_is_email(contact):
            return contact.strip()
        if self.partner_id and self.partner_id.email:
            return self.partner_id.email.strip()
        return ""

    def _signer_phone(self):
        self.ensure_one()
        contact = self._resolve_contact()
        if contact and not self._contact_is_email(contact):
            phone = contact
            if phone.lower().startswith("whatsapp:"):
                phone = phone.split(":", 1)[1]
            return phone.strip()
        if self.partner_id:
            return (
                getattr(self.partner_id, "mobile", None)
                or self.partner_id.phone
                or ""
            ).strip()
        return ""

    def _signer_name(self):
        self.ensure_one()
        return (
            self.partenaire_nom
            or (self.partner_id.name if self.partner_id else "")
            or self.etablissement
            or self.name
        )

    def _coins_is_quebec_entente(self, vals=None):
        """Marche Québec : devis CQ / entité Agence Doorway / fiche équipe Québec."""
        rec = self[:1]
        vals = vals or {}
        notes = (vals.get("notes") or (rec.notes if rec else "") or "").lower()
        if "cad" in notes or "québec" in notes or "quebec" in notes:
            return True
        if rec:
            order = self.env["sale.order"].sudo().search(
                [("coins_entente_id", "=", rec.id)], limit=1
            )
            if order:
                code = getattr(order, "ix_template_code", "") or ""
                if code.startswith("coins_quebec"):
                    return True
                if getattr(order, "ix_entity", "") == "agence_doorway":
                    return True
                if any(
                    (c or "").startswith("CQ_")
                    for c in order.order_line.mapped("product_id.default_code")
                ):
                    return True
            lead = self.env["crm.lead"].sudo().search(
                [("coins_entente_id", "=", rec.id)], limit=1
            )
            if lead and hasattr(lead, "_coins_is_quebec_market"):
                try:
                    if lead._coins_is_quebec_market():
                        return True
                except Exception:
                    pass
            if "coins.quebec.partenariat" in self.env:
                part = self.env["coins.quebec.partenariat"].sudo().search(
                    [("cq_entente_res_id", "=", rec.id)], limit=1
                )
                if part:
                    return True
        return False

    @api.model
    def _coins_default_clauses_html_from_vals(self, vals):
        if self._coins_is_quebec_entente(vals):
            return CLAUSES_HEBERGEMENT_QUEBEC_HTML
        return CLAUSES_HEBERGEMENT_HTML

    def _coins_default_clauses_html(self):
        if self and self._coins_is_quebec_entente():
            return CLAUSES_HEBERGEMENT_QUEBEC_HTML
        return CLAUSES_HEBERGEMENT_HTML

    def _coins_clauses_are_quebec(self, html):
        text = html or ""
        return "Agence Doorway" in text and "Coins Québec" in text

    @api.model
    def _fix_quebec_clauses_upgrade(self):
        """Upgrade : répare les ententes Québec non signées encore au texte Maroc."""
        from ..hooks import fix_quebec_entente_clauses

        fix_quebec_entente_clauses(self.env)

    def _get_signature_html(self):
        """Texte affiché sur le portail de signature — clauses + en-tête marque."""
        self.ensure_one()
        html = self.clauses_html or self._coins_default_clauses_html()
        if (
            not self.date_signature
            and self._coins_is_quebec_entente()
            and not self._coins_clauses_are_quebec(html)
        ):
            html = CLAUSES_HEBERGEMENT_QUEBEC_HTML
        inner = self._strip_clauses_internes(html)
        if self._coins_is_quebec_entente():
            title = (
                "Entente Channel Manager"
                if self.type_partenaire == "hebergement"
                else "Entente de visibilité"
            )
            return (
                '<div style="font-family:Georgia,Times,serif;color:#1F2A1E;">'
                '<div style="background:#1F2A1E;color:#F5F1E6;padding:20px 22px;'
                'margin:0 0 22px;border-radius:6px;">'
                '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;'
                'color:#D9A94D;">Coins Québec</div>'
                '<div style="font-size:22px;margin-top:6px;">%s</div>'
                '<div style="font-size:13px;color:#D9A94D;margin-top:8px;">'
                "Agence Doorway · Montréal</div>"
                "</div>%s</div>"
            ) % (title, inner)
        return inner

    def _strip_clauses_internes(self, html):
        """Retire avertissement avocat et notes internes si collés par erreur."""
        fallback = self._coins_default_clauses_html()
        if not html:
            return fallback
        cleaned = re.sub(
            r"<blockquote[\s\S]*?</blockquote>",
            "",
            html,
            flags=re.I,
        )
        cleaned = re.sub(
            r"(?is)<h[1-6][^>]*>\s*Points à valider[\s\S]*$",
            "",
            cleaned,
        )
        markers = (
            "avis juridique",
            "révisé par un avocat",
            "revise par un avocat",
            "points à valider avec vous",
        )
        lower = cleaned.lower()
        if any(m in lower for m in markers):
            return fallback
        return cleaned

    def _coins_prepare_signature(self):
        """Prépare pe.electronic.signature — même moteur /sign/contract/<token>."""
        self.ensure_one()
        if self.signature_id or self.date_signature:
            return self.signature_id
        if not self.clauses_html:
            self.clauses_html = self._coins_default_clauses_html()
        elif (
            not self.date_signature
            and self._coins_is_quebec_entente()
            and not self._coins_clauses_are_quebec(self.clauses_html)
        ):
            self.clauses_html = CLAUSES_HEBERGEMENT_QUEBEC_HTML
        else:
            self.clauses_html = self._strip_clauses_internes(self.clauses_html)
        if "pe.electronic.signature" not in self.env:
            raise UserError(
                _("Le module de signature électronique n'est pas installé.")
            )
        email = self._signer_email()
        phone = self._signer_phone()
        Sig = self.env["pe.electronic.signature"].sudo()
        signer_name = self._signer_name()
        if self._coins_is_quebec_entente() and self.type_partenaire != "hebergement":
            doc_name = _("Entente visibilité Coins Québec — %s") % (
                self.etablissement or signer_name
            )
        else:
            doc_name = _("Entente Channel Manager — %s") % (
                self.etablissement or signer_name
            )
        if hasattr(Sig, "create_for_document"):
            sig = Sig.create_for_document(
                self,
                signer_email=email or False,
                signer_name=signer_name,
                document_name=doc_name,
                signer_phone=phone or False,
            )
        else:
            sig = Sig.create(
                {
                    "res_model": self._name,
                    "res_id": self.id,
                    "signer_email": email or False,
                    "signer_name": signer_name,
                    "document_name": doc_name,
                    "signer_phone": phone or False,
                }
            )
        self.write(
            {
                "statut_entente": "en_attente_signature",
                "signature_id": sig.id,
                "token_signature": getattr(sig, "token", False) or False,
            }
        )
        return sig

    def action_envoyer_signature(self):
        self.ensure_one()
        if self.date_signature:
            raise UserError(_("Cette entente est déjà signée."))
        email = self._signer_email()
        phone = self._signer_phone()
        if not email and not phone:
            raise UserError(
                _(
                    "Renseignez l'email ou le téléphone WhatsApp du partenaire "
                    "(champ Contact partenaire)."
                )
            )
        sig = self._coins_prepare_signature()
        if hasattr(sig, "action_send_signature_request"):
            sig.action_send_signature_request()
        self.write({"date_envoi_signature": fields.Datetime.now()})
        self.message_post(
            body=_("Demande de signature électronique envoyée à %s.")
            % (email or phone)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Signature envoyée"),
                "message": _("Le partenaire peut valider l'entente par OTP."),
                "type": "success",
                "sticky": False,
            },
        }

    def _on_electronic_signed(self, signature):
        """Callback people_engine après OTP OK."""
        self.ensure_one()
        html = self._get_signature_html()
        cert = ""
        if signature and getattr(signature, "signature_certificate", None):
            cert = signature.signature_certificate
        payload = (
            "<html><body>%s<hr/><pre>%s</pre></body></html>" % (html, cert)
        ).encode("utf-8")
        token = ""
        if signature:
            token = getattr(signature, "token", "") or ""
        self.write(
            {
                "statut_entente": "active",
                "date_signature": fields.Datetime.now(),
                "pdf_signe": base64.b64encode(payload),
                "pdf_signe_filename": "%s-signee.html" % (self.name or "entente"),
                "token_signature": token or self.token_signature,
            }
        )
        self.message_post(
            body=_("Entente %s signée électroniquement.") % self.name
        )
        self._planifier_demarrage()
        self._envoyer_acces_partenaire()
        try:
            self._coins_after_signed_won_and_invoice()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("post-signature won/facture site: %s", exc)
            self.message_post(
                body=_(
                    "Signature OK, mais le passage gagné / la facture site "
                    "a échoué : %s"
                )
                % exc
            )

    def _planifier_demarrage(self):
        self.ensure_one()
        lieu = self.etablissement or self.partenaire_nom or self.name
        if self.shooting_souhaite:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=self.env.user.id,
                summary=_("Tournage photo/vidéo — %s") % lieu,
                note=_(
                    "Shooting inclus, sans frais. Convenez d'un créneau "
                    "avec le partenaire et facilitez l'accès aux lieux."
                ),
            )
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.env.user.id,
            summary=_("Channel Manager / conciergerie — %s") % lieu,
            note=_(
                "Connecter Booking.com et/ou Airbnb par autorisation officielle "
                "(jamais le mot de passe). Vérifier si un autre Channel Manager "
                "est déjà connecté avant de basculer."
            ),
        )

    def _envoyer_acces_partenaire(self):
        self.ensure_one()
        email = self._signer_email()
        if not email:
            self.message_post(
                body=_(
                    "Signature OK, mais aucun email : accès portail non envoyé."
                )
            )
            return
        Partner = self.env["res.partner"].sudo()
        partner = self.partner_id
        if not partner:
            partner = Partner.search([("email", "=ilike", email)], limit=1)
        if not partner:
            partner = Partner.create(
                {
                    "name": self._signer_name(),
                    "email": email,
                    "phone": self._signer_phone() or False,
                    "comment": _("Partenaire hébergement Coins Marocain — %s")
                    % (self.name or ""),
                }
            )
        if self.partner_id != partner:
            self.partner_id = partner.id
        self._accorder_acces_portail(partner)
        template = self.env.ref(
            "coins_marocain_partenariats.mail_template_hebergement_acces",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)

    def _accorder_acces_portail(self, partner):
        if partner.user_ids:
            return
        portal_group = self.env.ref("base.group_portal", raise_if_not_found=False)
        if not portal_group:
            return
        if hasattr(partner, "action_grant_access"):
            try:
                partner.sudo().action_grant_access()
                return
            except Exception:
                _logger.exception(
                    "action_grant_access portail échoué pour %s", partner.id
                )
        Users = self.env["res.users"].sudo()
        if Users.search([("login", "=", partner.email)], limit=1):
            return
        Users.with_context(no_reset_password=False).create(
            {
                "name": partner.name,
                "login": partner.email,
                "email": partner.email,
                "partner_id": partner.id,
                "groups_id": [(6, 0, [portal_group.id])],
            }
        )

    def _coins_related_crm_lead(self):
        self.ensure_one()
        Lead = self.env["crm.lead"].sudo()
        lead = Lead.search([("coins_entente_id", "=", self.id)], limit=1)
        if lead:
            return lead
        if self.partner_id:
            return Lead.search(
                [
                    ("partner_id", "=", self.partner_id.id),
                    ("team_id.name", "ilike", "Coins Marocain"),
                ],
                limit=1,
            )
        return Lead.browse()

    def _coins_related_cq_partenariat(self):
        self.ensure_one()
        if "coins.quebec.partenariat" not in self.env:
            return self.env["coins.quebec.partenariat"].browse()
        return (
            self.env["coins.quebec.partenariat"]
            .sudo()
            .search([("cq_entente_res_id", "=", self.id)], limit=1)
        )

    def _coins_won_stage_for_lead(self, lead):
        Stage = self.env["crm.stage"].sudo()
        team = lead.team_id
        domain_won = [("is_won", "=", True)]
        if team and "team_ids" in Stage._fields:
            stage = Stage.search(
                domain_won + [("team_ids", "in", [team.id])],
                limit=1,
                order="sequence",
            )
            if stage:
                return stage
        return Stage.search(domain_won, limit=1, order="sequence")

    def _coins_mark_pipeline_won(self):
        """Fiche CRM / CQ → gagné dès que l'entente est signée."""
        self.ensure_one()
        lead = self._coins_related_crm_lead()
        if lead and not lead.stage_id.is_won:
            stage = self._coins_won_stage_for_lead(lead)
            if stage:
                lead.write({"stage_id": stage.id})
                lead.message_post(
                    body=_("Stage Gagné — entente %s signée.") % (self.name or "")
                )
        cq = self._coins_related_cq_partenariat()
        if cq and cq.stage != "gagne":
            cq.write({"stage": "gagne"})
            cq.message_post(
                body=_("Stage Gagné — entente %s signée.") % (self.name or "")
            )

    def _coins_parse_site_forfait(self):
        """Montant forfait site dans les clauses (pas le catalogue 4 000 DH)."""
        self.ensure_one()
        html = self.clauses_html or ""
        text = re.sub(r"<[^>]+>", " ", html)
        text = (
            text.replace("\xa0", " ")
            .replace("&nbsp;", " ")
            .replace("&#160;", " ")
        )
        text = re.sub(r"\s+", " ", text)
        # Le catalogue (4 000 DH) n'est pas le forfait négocié.
        text = re.sub(
            r"catalogue\s+\d[\d ]{0,6}\s*(?:DH|MAD|CAD|\$)",
            "",
            text,
            flags=re.I,
        )
        patterns = (
            r"facture de\s+(\d[\d ]{0,6})\s*(?:DH|MAD|CAD|\$)",
            r"(?:site|refonte)[^.]{0,220}?(\d[\d ]{0,6})\s*(?:DH|MAD|CAD|\$)",
            r"(\d[\d ]{0,6})\s*(?:DH|MAD|CAD|\$)\s*[^.]{0,80}(?:site|refonte)",
        )
        for pat in patterns:
            match = re.search(pat, text, flags=re.I)
            if not match:
                continue
            raw = match.group(1).replace(" ", "")
            try:
                amount = float(raw)
            except ValueError:
                continue
            if 100 <= amount <= 50000:
                return amount
        lead = self._coins_related_crm_lead()
        if lead and getattr(lead, "coins_xsell_site_web", False):
            product = self.env["product.product"].sudo().search(
                [("default_code", "=", "CM_SITE_CREATION")], limit=1
            )
            if product:
                return float(product.list_price or 0.0)
        return 0.0

    def _coins_existing_site_invoice(self):
        self.ensure_one()
        origin = "%s-site" % (self.name or "")
        return self.env["account.move"].sudo().search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "!=", "cancel"),
                "|",
                "|",
                ("invoice_origin", "=", origin),
                ("invoice_origin", "=", self.name),
                ("invoice_origin", "=", "Entente %s" % (self.name or "")),
            ],
            limit=1,
        )

    def _coins_invoice_company_and_currency(self):
        self.ensure_one()
        quebec = self._coins_is_quebec_entente()
        Company = self.env["res.company"].sudo()
        if quebec:
            company = Company.search([("name", "ilike", "Agence Doorway")], limit=1)
        else:
            company = Company.search([("name", "ilike", "Digital Doorway")], limit=1)
        if not company:
            company = self.env.company
        currency = company.currency_id
        if not quebec:
            mad = self.env["res.currency"].sudo().search(
                [("name", "=", "MAD")], limit=1
            )
            if mad:
                currency = mad
        return company, currency

    def _coins_ensure_invoice_accounts(self, company, partner):
        """Réactive les comptes produits / clients archivés (CoA Maroc)."""
        Account = (
            self.env["account.account"]
            .sudo()
            .with_company(company)
            .with_context(active_test=False)
        )
        income = Account.search(
            [
                ("account_type", "=", "income"),
                ("active", "=", True),
                ("company_ids", "in", [company.id]),
            ],
            limit=1,
        )
        if not income:
            domain = [
                ("account_type", "=", "income"),
                ("company_ids", "in", [company.id]),
            ]
            if not self._coins_is_quebec_entente():
                income = Account.search(
                    domain + [("code", "=", "712430")], limit=1
                )
            if not income:
                income = Account.search(domain, limit=1)
            if income and not income.active:
                income.sudo().write({"active": True})
        receivable = partner.with_company(company).property_account_receivable_id
        if receivable and not receivable.active:
            receivable.sudo().write({"active": True})
        if not receivable or not receivable.active:
            receivable = Account.search(
                [
                    ("account_type", "=", "asset_receivable"),
                    ("company_ids", "in", [company.id]),
                ],
                limit=1,
            )
            if receivable and not receivable.active:
                receivable.sudo().write({"active": True})
            if receivable:
                partner.with_company(company).sudo().write(
                    {"property_account_receivable_id": receivable.id}
                )
        vat_accs = Account.search(
            [
                ("code", "like", "4455%"),
                ("company_ids", "in", [company.id]),
            ]
        )
        for vat_acc in vat_accs:
            if not vat_acc.active:
                vat_acc.sudo().write({"active": True})
        return income, receivable

    def _coins_site_invoice_taxes(self, company, quebec):
        Tax = self.env["account.tax"].sudo().with_company(company)
        if quebec:
            tax = Tax.search(
                [
                    ("company_id", "=", company.id),
                    ("type_tax_use", "=", "sale"),
                    ("name", "ilike", "TPS + TVQ"),
                ],
                limit=1,
            )
            if tax:
                return tax
            return Tax.search(
                [
                    ("company_id", "=", company.id),
                    ("type_tax_use", "=", "sale"),
                    ("amount", ">", 0),
                ]
            )
        tax = company.account_sale_tax_id
        if tax and tax.company_id == company and tax.amount == 20:
            return tax
        return Tax.search(
            [
                ("company_id", "=", company.id),
                ("type_tax_use", "=", "sale"),
                ("amount", "=", 20),
            ],
            limit=1,
        )

    def _coins_site_line_price(self, amount, taxes, currency, quebec):
        """Forfait signé = HT. TVA / TPS-TVQ en sus (CM 20 %, CQ taxes QC)."""
        return amount

    def _coins_site_invoice_all_lines(self, quebec, lieu, price_unit, taxes, income):
        """Forfait site (HT + taxe) + commissions à 0 et inclusions."""
        def _line(name, price, tax_ids):
            vals = {
                "name": name,
                "quantity": 1.0,
                "price_unit": price,
                "tax_ids": [(6, 0, tax_ids)],
            }
            if income:
                vals["account_id"] = income.id
            return (0, 0, vals)

        lines = [
            _line(
                self._coins_site_invoice_line_name(quebec, lieu),
                price_unit,
                taxes.ids,
            )
        ]
        if quebec:
            lines.append(
                _line(
                    _(
                        "Visibilité Coins Québec — commission 15 %%\n"
                        "Événements, groupes et références. Sans frais fixe.\n"
                        "0,00 $ CAD sur cette facture — facturée sur les "
                        "réservations réelles uniquement."
                    ),
                    0.0,
                    [],
                )
            )
            lines.append(
                _line(
                    _(
                        "Digitalisation / Channel Manager — commission 10 %%\n"
                        "Aucun abonnement mensuel.\n"
                        "0,00 $ CAD sur cette facture — facturée sur les "
                        "réservations réelles uniquement."
                    ),
                    0.0,
                    [],
                )
            )
        else:
            lines.append(
                _line(
                    _(
                        "Module hébergement — visibilité Coins Marocain et "
                        "Coins Québec\n"
                        "Inclus : événements, groupes et références. "
                        "Sans frais fixe à la signature.\n"
                        "Commission 15 %% — 0,00 DH sur cette facture.\n"
                        "Facturée uniquement sur les réservations réelles "
                        "(hors annulations remboursées)."
                    ),
                    0.0,
                    [],
                )
            )
            lines.append(
                _line(
                    _(
                        "Channel Manager (Channex) — Booking.com et/ou Airbnb\n"
                        "Inclus : connexion par autorisation officielle "
                        "(jamais le mot de passe). Aucun abonnement mensuel.\n"
                        "Commission 10 %% — 0,00 DH sur cette facture.\n"
                        "En plus de la commission plateforme, sur "
                        "réservations réelles uniquement."
                    ),
                    0.0,
                    [],
                )
            )
            lines.append(
                _line(
                    _(
                        "Shooting photo/vidéo — inclus, sans frais\n"
                        "Programmé selon les disponibilités. Propriété du "
                        "partenaire ; droit d'usage Coins Marocain."
                    ),
                    0.0,
                    [],
                )
            )
        return lines

    def _coins_site_invoice_line_name(self, quebec, lieu):
        if quebec:
            return (
                _("Création du site web — %s\n"
                  "Forfait négocié.\n"
                  "Inclus : conception et maquette ; pages accueil, offre, "
                  "réservation, contact ; mise en ligne.")
                % lieu
            )
        return (
            _("Refonte du site web — %s\n"
              "Forfait négocié (catalogue 4 000 DH).\n"
              "Détail de la prestation :\n"
              "• Conception et maquette du site\n"
              "• Pages accueil, chambres / suites, réservation, contact\n"
              "• Reprise des photos et du contenu du site actuel\n"
              "• Mise en ligne")
            % lieu
        )

    def _coins_ensure_doorway_bank(self, company, quebec):
        PartnerBank = self.env["res.partner.bank"].sudo()
        existing = PartnerBank.search(
            [
                ("partner_id", "=", company.partner_id.id),
                "|",
                ("company_id", "=", company.id),
                ("company_id", "=", False),
            ],
            limit=1,
        )
        if not existing:
            existing = PartnerBank.search(
                [("sanitized_acc_number", "=", "007780000115500000197212")],
                limit=1,
            )
        if existing:
            return existing
        if quebec:
            return PartnerBank.browse()
        morocco = self.env["res.country"].sudo().search(
            [("code", "=", "MA")], limit=1
        )
        Bank = self.env["res.bank"].sudo()
        bank = Bank.search([("bic", "=", "BCMAMAMC")], limit=1)
        if not bank:
            bank = Bank.create(
                {
                    "name": "Attijariwafa bank",
                    "bic": "BCMAMAMC",
                    "street": "Angle rue Al Fourate et R. Imran Alfasi, Maarif",
                    "city": "Casablanca",
                    "country": morocco.id if morocco else False,
                }
            )
        vals = {
            "acc_number": "007 780 0001155000001972 12",
            "acc_holder_name": "DIGITAL DOORWAY",
            "bank_id": bank.id,
            "partner_id": company.partner_id.id,
            "company_id": company.id,
        }
        if "allow_out_payment" in PartnerBank._fields:
            vals["allow_out_payment"] = True
        return PartnerBank.create(vals)

    def _coins_enrich_invoice_partner(self, partner):
        """Complète la fiche client (adresse, pays, téléphone, contact)."""
        self.ensure_one()
        if not partner:
            return partner
        lead = self._coins_related_crm_lead()
        quebec = self._coins_is_quebec_entente()
        country = self.env["res.country"].sudo().search(
            [("code", "=", "CA" if quebec else "MA")], limit=1
        )
        vals = {}
        street = ""
        if lead:
            street = lead.street or ""
        if not partner.street and street:
            vals["street"] = street
        street2 = ""
        if lead:
            street2 = (
                getattr(lead, "street2", None)
                or getattr(lead, "coins_quartier", None)
                or ""
            )
        if not partner.street2 and street2:
            vals["street2"] = street2
        city = ""
        if lead:
            city = (
                lead.city
                or getattr(lead, "coins_ville_autre", None)
                or ""
            )
            if not city and getattr(lead, "coins_ville", None):
                city = dict(
                    lead._fields["coins_ville"].selection
                ).get(lead.coins_ville) or lead.coins_ville
        if not partner.city and city:
            vals["city"] = city
        if not partner.zip and lead and lead.zip:
            vals["zip"] = lead.zip
        if not partner.country_id and country:
            vals["country_id"] = country.id
        email = self._signer_email() or (lead.email_from if lead else "")
        if email and not partner.email:
            vals["email"] = email
        phone = self._signer_phone() or (lead.phone if lead else "")
        if phone and not partner.phone:
            vals["phone"] = phone
        website = ""
        if lead:
            website = getattr(lead, "website", None) or ""
        if website and not partner.website:
            vals["website"] = website
        if not partner.lang:
            vals["lang"] = "fr_FR" if not quebec else "fr_CA"
        if "is_company" in partner._fields and not partner.is_company:
            vals["is_company"] = True
        if vals:
            partner.sudo().write(vals)
        signer = self._signer_name() or (lead.contact_name if lead else "")
        if signer and signer.lower() not in (partner.name or "").lower():
            child = partner.child_ids.filtered(
                lambda c: (c.name or "").lower() == signer.lower()
            )[:1]
            if not child:
                partner.sudo().write(
                    {
                        "child_ids": [
                            (
                                0,
                                0,
                                {
                                    "name": signer,
                                    "type": "contact",
                                    "email": email or False,
                                    "phone": phone or False,
                                },
                            )
                        ]
                    }
                )
        return partner

    def _coins_invoice_payment_narration(self, move, quebec):
        if quebec:
            return _(
                "<p><strong>Paiement Québec</strong> — Stripe ou Interac "
                "e-Transfer à comptabilite@agencedoorway.com<br/>"
                "Référence : %s<br/>"
                "Commissions : facture mensuelle séparée, "
                "sur réservations réelles.</p>"
            ) % (move.name or "")
        return _(
            "<p><strong>Paiement Maroc — virement instantané "
            "(pas de carte)</strong></p>"
            "<p>"
            "Titulaire : DIGITAL DOORWAY<br/>"
            "Banque : Attijariwafa bank<br/>"
            "Domiciliation : CASA AL FOURATE, "
            "Angle rue Al Fourate et R. Imran Alfasi, Maarif<br/>"
            "RIB : 007 780 0001155000001972 12<br/>"
            "IBAN : MA64 0077 8000 0115 5000 0019 7212<br/>"
            "BIC : BCMAMAMC<br/>"
            "Référence : %s"
            "</p>"
            "<p>Commissions 10 %% / 15 %% : facture mensuelle séparée, "
            "uniquement sur réservations réelles.</p>"
        ) % (move.name or "")

    def _coins_ensure_letterhead(self, company, quebec):
        """En-tête facture : Digital Doorway (CM) ou Agence Doorway (CQ)."""
        details = company.company_details or ""
        if quebec:
            if "agence doorway" in details.lower() and "False" not in details:
                return
            html = (
                "<p>Agence Doorway Inc.<br/>"
                "204 rue du Saint-Sacrement, espace 300,<br/>"
                "Montréal H2Y 1W8<br/>"
                "Canada</p>"
            )
        else:
            if (
                "digital doorway" in details.lower()
                and "False" not in details
                and "ICE:" not in details
            ):
                return
            html = (
                "<p>Digital Doorway SARL<br/>"
                "77 rue Mohamed Smiha, 8ème étage<br/>"
                "Casablanca<br/>"
                "Maroc</p>"
            )
        company.sudo().write({"company_details": html})

    def _coins_rewrite_site_invoice(self, move, amount):
        """Met à jour une facture site déjà créée (TVA, détail, RIB, en-tête)."""
        self.ensure_one()
        partner = self._coins_enrich_invoice_partner(move.partner_id)
        company, currency = self._coins_invoice_company_and_currency()
        quebec = self._coins_is_quebec_entente()
        self._coins_ensure_letterhead(company, quebec)
        taxes = self._coins_site_invoice_taxes(company, quebec)
        price_unit = self._coins_site_line_price(amount, taxes, currency, quebec)
        lieu = self.etablissement or self.partenaire_nom or partner.name
        income, _receivable = self._coins_ensure_invoice_accounts(company, partner)
        bank = self._coins_ensure_doorway_bank(company, quebec)
        if move.state == "posted":
            move.button_draft()
        move.invoice_line_ids.unlink()
        vals = {
            "company_id": company.id,
            "partner_id": partner.id,
            "invoice_origin": "Entente %s" % (self.name or ""),
            "invoice_line_ids": self._coins_site_invoice_all_lines(
                quebec, lieu, price_unit, taxes, income
            ),
        }
        if bank:
            vals["partner_bank_id"] = bank.id
        move.write(vals)
        move.narration = self._coins_invoice_payment_narration(move, quebec)
        if move.state != "posted":
            move.action_post()
        return move

    def _coins_create_site_invoice(self, amount):
        """Facture forfait site uniquement — pas les commissions 10/15 %."""
        self.ensure_one()
        existing = self._coins_existing_site_invoice()
        if existing:
            return existing
        partner = self.partner_id or self._coins_related_crm_lead().partner_id
        if not partner:
            raise UserError(
                _("Pas de fiche contact pour facturer le site (%s).") % self.name
            )
        partner = self._coins_enrich_invoice_partner(partner)
        company, currency = self._coins_invoice_company_and_currency()
        quebec = self._coins_is_quebec_entente()
        self._coins_ensure_letterhead(company, quebec)
        code = "CQ_SITE_CREATION" if quebec else "CM_SITE_CREATION"
        product = self.env["product.product"].sudo().search(
            [("default_code", "=", code)], limit=1
        )
        if not product and not quebec:
            product = self.env["product.product"].sudo().search(
                [("default_code", "=", "CM_SITE_CREATION")], limit=1
            )
        lieu = self.etablissement or self.partenaire_nom or partner.name
        taxes = self._coins_site_invoice_taxes(company, quebec)
        price_unit = self._coins_site_line_price(amount, taxes, currency, quebec)
        Move = self.env["account.move"].sudo().with_company(company)
        income, receivable = self._coins_ensure_invoice_accounts(company, partner)
        lines = self._coins_site_invoice_all_lines(
            quebec, lieu, price_unit, taxes, income
        )
        if product and lines:
            lines[0][2]["product_id"] = product.id
        bank = self._coins_ensure_doorway_bank(company, quebec)
        vals = {
            "move_type": "out_invoice",
            "company_id": company.id,
            "partner_id": partner.id,
            "invoice_origin": "Entente %s" % (self.name or ""),
            "invoice_date": fields.Date.context_today(self),
            "currency_id": currency.id,
            "invoice_user_id": (
                self._coins_related_crm_lead().user_id.id
                or self.env.user.id
            ),
            "invoice_line_ids": lines,
        }
        if bank:
            vals["partner_bank_id"] = bank.id
        move = Move.create(vals)
        move.narration = self._coins_invoice_payment_narration(move, quebec)
        move.action_post()
        self.message_post(
            body=_(
                "Facture site générée automatiquement : %s — %s %s."
            )
            % (move.name, amount, currency.name)
        )
        lead = self._coins_related_crm_lead()
        if lead:
            if "coins_xsell_site_web" in lead._fields and not lead.coins_xsell_site_web:
                lead.coins_xsell_site_web = True
            lead.message_post(
                body=_("Facture site %s (%s %s) — entente signée.")
                % (move.name, amount, currency.name)
            )
        self._coins_send_site_invoice(move)
        return move

    def _coins_invoice_portal_url(self, move):
        move._portal_ensure_token()
        return move.get_base_url().rstrip("/") + (move.get_portal_url() or "")

    def _coins_invoice_mail_server(self, quebec):
        MailServer = self.env["ir.mail_server"].sudo()
        needles = (
            ("info@coinsquebec.com", "martin@agencedoorway.com")
            if quebec
            else ("zakaria@coinsmarocain.com", "zakaria@agencedoorway.com")
        )
        for needle in needles:
            server = MailServer.search(
                [("from_filter", "ilike", needle)], limit=1
            )
            if server:
                return server
        return MailServer.browse()

    def _coins_send_site_invoice(self, move, force=False):
        """Envoie la facture site (PDF + lien portail). Idempotent."""
        self.ensure_one()
        if not move:
            return False
        email = (move.partner_id.email or self._signer_email() or "").strip()
        if not email:
            self.message_post(
                body=_("Facture %s créée, mais aucun email pour l'envoyer.")
                % (move.name or "")
            )
            return False
        already = self.env["mail.mail"].sudo().search(
            [
                ("model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("state", "in", ("sent", "outgoing")),
            ],
            limit=1,
        )
        if not force and (already or getattr(move, "is_move_sent", False)):
            url = self._coins_invoice_portal_url(move)
            self.message_post(
                body=_("Facture déjà envoyée (%s). Lien : %s")
                % (move.name, url)
            )
            return already
        quebec = self._coins_is_quebec_entente()
        url = self._coins_invoice_portal_url(move)
        brand = "Coins Québec" if quebec else "Coins Marocain"
        accent = "#1F2A1E" if quebec else "#b5732f"
        bouton = "#D9A94D" if quebec else "#b5732f"
        bouton_txt = "#1F2A1E" if quebec else "#ffffff"
        lieu = self.etablissement or self.partenaire_nom or move.partner_id.name
        prenom = self._signer_name() or move.partner_id.name or "partenaire"
        amount = "%.2f %s" % (move.amount_total, move.currency_id.name)
        if quebec:
            email_from = "Coins Québec <info@coinsquebec.com>"
            paiement = (
                "Paiement Québec : Stripe (carte) ou Interac e-Transfer "
                "à comptabilite@agencedoorway.com. Référence : %s."
            ) % (move.name,)
            signature = "Coins Québec — Agence Doorway Inc."
        else:
            email_from = "Zakaria <zakaria@coinsmarocain.com>"
            paiement = (
                "Paiement Maroc — virement instantané uniquement (pas de carte) :<br/>"
                "Titulaire : DIGITAL DOORWAY<br/>"
                "Banque : Attijariwafa bank<br/>"
                "Domiciliation : CASA AL FOURATE, Angle rue Al Fourate et "
                "R. Imran Alfasi, Maarif<br/>"
                "RIB : 007 780 0001155000001972 12<br/>"
                "IBAN : MA64 0077 8000 0115 5000 0019 7212<br/>"
                "BIC : BCMAMAMC<br/>"
                "Référence : %s."
            ) % (move.name,)
            signature = "Zakaria<br/>Coins Marocain — Digital Doorway SARL"
        body = """
<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:22px;color:#262220;max-width:600px;">
  <p>Bonjour <strong>%s</strong>,</p>
  <p>
    Voici la facture <strong>%s</strong> pour la création / refonte du site
    <strong>%s</strong> : <strong>%s</strong>.
  </p>
  <p style="text-align:center;margin:24px 0;">
    <a href="%s"
       style="background:%s;color:%s;padding:12px 22px;text-decoration:none;border-radius:4px;font-weight:600;display:inline-block;">
      Voir la facture
    </a>
  </p>
  <p>Lien : <a href="%s" style="color:%s;">%s</a></p>
  <p>%s</p>
  <p>Le PDF est aussi joint à cet e-mail.</p>
  <p>À très vite,<br/>%s</p>
</div>
""" % (
            prenom,
            move.name,
            lieu,
            amount,
            url,
            bouton,
            bouton_txt,
            url,
            accent,
            url,
            paiement,
            signature,
        )
        pdf_content = b""
        try:
            pdf_content, _unused = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
                "account.account_invoices", [move.id]
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("PDF facture site %s: %s", move.name, exc)
        filename = "%s.pdf" % ((move.name or "facture").replace("/", "-"))
        attach_vals = []
        if pdf_content:
            attach_vals.append(
                (
                    0,
                    0,
                    {
                        "name": filename,
                        "type": "binary",
                        "datas": base64.b64encode(pdf_content),
                        "mimetype": "application/pdf",
                        "res_model": "account.move",
                        "res_id": move.id,
                    },
                )
            )
        vals = {
            "subject": _("%s — facture %s · %s") % (brand, move.name, lieu),
            "email_from": email_from,
            "email_to": email,
            "body_html": body,
            "model": "account.move",
            "res_id": move.id,
            "auto_delete": False,
            "attachment_ids": attach_vals,
        }
        server = self._coins_invoice_mail_server(quebec)
        if server:
            vals["mail_server_id"] = server.id
            if not quebec:
                vals["email_from"] = "Zakaria <zakaria@agencedoorway.com>"
        mail = self.env["mail.mail"].sudo().create(vals)
        mail.send()
        if "is_move_sent" in move._fields:
            move.sudo().is_move_sent = True
        note = _("Facture %s envoyée à %s. Lien : %s") % (move.name, email, url)
        self.message_post(body=note)
        move.message_post(body=note)
        lead = self._coins_related_crm_lead()
        if lead:
            lead.message_post(body=note)
        return mail

    def _coins_after_signed_won_and_invoice(self):
        """Après OTP : pipeline gagné + facture site si forfait dans l'entente.

        Même enchaînement CM et CQ. Les commissions ne sont pas facturées ici.
        """
        self.ensure_one()
        self._coins_mark_pipeline_won()
        amount = self._coins_parse_site_forfait()
        if amount <= 0:
            self.message_post(
                body=_(
                    "Aucun forfait site détecté dans l'entente — "
                    "pas de facture à la signature."
                )
            )
            return False
        return self._coins_create_site_invoice(amount)
