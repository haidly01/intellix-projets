# -*- coding: utf-8 -*-
import json
import logging
import re
from html import unescape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _strip_html(html):
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html or "")
    return unescape(re.sub(r"\s+", " ", text)).strip()


class DoorwayMessageCampaign(models.Model):
    _name = "doorway.message.campaign"
    _description = "Campagne de messagerie multi-canal"
    _order = "date_planned desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char("Nom de la campagne", required=True, tracking=True)
    statut = fields.Selection(
        [
            ("brouillon", "Brouillon"),
            ("planifie", "Planifié"),
            ("en_cours", "En cours"),
            ("termine", "Terminé"),
            ("erreur", "Erreur partielle"),
        ],
        default="brouillon",
        tracking=True,
    )

    sujet = fields.Char("Sujet (Email)")
    corps_master = fields.Html(
        "Message maître",
        help="Contenu de base — adapté par canal automatiquement",
    )

    corps_email = fields.Html("Version Email")
    corps_sms = fields.Text("Version SMS (160 car max)")
    corps_whatsapp = fields.Text("Version WhatsApp")
    corps_linkedin = fields.Text("Version LinkedIn (3 000 car max)")
    corps_gmb = fields.Text("Version Google My Business (1 500 car max)")

    canal_email = fields.Boolean("Email")
    canal_sms = fields.Boolean("SMS")
    canal_whatsapp = fields.Boolean("WhatsApp")
    canal_linkedin = fields.Boolean("LinkedIn")
    canal_gmb = fields.Boolean("Google My Business")

    whatsapp_template_id = fields.Many2one(
        "doorway.message.template",
        string="Template WhatsApp approuvé",
        domain="[('canal', '=', 'whatsapp'), ('is_twilio_ready', '=', True)]",
        help="Template Twilio approuvé utilisé pour l'envoi WhatsApp à l'initiative "
        "de l'entreprise (obligatoire hors fenêtre de session 24h).",
    )
    sms_template_id = fields.Many2one(
        "doorway.message.template",
        string="Template SMS",
        domain="[('canal', '=', 'sms')]",
        help="Template Twilio Content optionnel pour le SMS.",
    )

    lead_ids = fields.Many2many(
        "crm.lead",
        "doorway_msg_campaign_lead_rel",
        "campaign_id",
        "lead_id",
        string="Leads CRM",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "doorway_msg_campaign_partner_rel",
        "campaign_id",
        "partner_id",
        string="Contacts",
    )
    emails_manuels = fields.Text("Emails manuels (un par ligne)")
    phones_manuels = fields.Text("Téléphones manuels (un par ligne)")

    envoi_immediat = fields.Boolean("Envoyer immédiatement", default=True)
    date_planned = fields.Datetime("Date d'envoi planifiée")

    linkedin_page_id = fields.Many2one(
        "doorway.channel.config",
        domain=[("canal", "=", "linkedin"), ("actif", "=", True)],
        string="Page LinkedIn",
    )
    linkedin_type = fields.Selection(
        [
            ("personal", "Profil personnel"),
            ("company", "Page entreprise"),
        ],
        default="company",
    )

    gmb_location_id = fields.Many2one(
        "doorway.channel.config",
        domain=[("canal", "=", "gmb"), ("actif", "=", True)],
        string="Établissement GMB",
    )
    gmb_post_type = fields.Selection(
        [
            ("STANDARD", "Post standard"),
            ("EVENT", "Événement"),
            ("OFFER", "Offre"),
        ],
        default="STANDARD",
    )

    nb_destinataires = fields.Integer(
        "Destinataires", compute="_compute_stats", store=True
    )
    nb_envoyes = fields.Integer("Envoyés", readonly=True)
    nb_erreurs = fields.Integer("Erreurs", readonly=True)
    nb_lus = fields.Integer("Lus / Ouverts", readonly=True)

    log_ids = fields.One2many("doorway.message.log", "campaign_id", string="Logs")
    date_creation = fields.Datetime(default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    @api.depends(
        "lead_ids",
        "partner_ids",
        "emails_manuels",
        "phones_manuels",
        "canal_email",
        "canal_sms",
        "canal_whatsapp",
        "canal_linkedin",
        "canal_gmb",
    )
    def _compute_stats(self):
        for rec in self:
            rec.nb_destinataires = len(rec._collect_recipients())

    def _active_canaux(self):
        self.ensure_one()
        canaux = []
        if self.canal_email:
            canaux.append("email")
        if self.canal_sms:
            canaux.append("sms")
        if self.canal_whatsapp:
            canaux.append("whatsapp")
        if self.canal_linkedin:
            canaux.append("linkedin")
        if self.canal_gmb:
            canaux.append("gmb")
        return canaux

    def _collect_recipients(self):
        """Retourne une liste de dicts {email, phone, lead_id, partner_id, name}."""
        self.ensure_one()
        seen_email, seen_phone = set(), set()
        out = []

        def add(email="", phone="", lead=None, partner=None, name=""):
            email = (email or "").strip().lower()
            phone = re.sub(r"[^\d+]", "", phone or "")
            key = email or phone
            if not key:
                return
            if email and email in seen_email:
                return
            if phone and phone in seen_phone:
                return
            if email:
                seen_email.add(email)
            if phone:
                seen_phone.add(phone)
            out.append(
                {
                    "email": email,
                    "phone": phone,
                    "lead_id": lead.id if lead else False,
                    "partner_id": partner.id if partner else False,
                    "name": name or email or phone,
                }
            )

        for lead in self.lead_ids:
            add(
                email=lead.email_from,
                phone=lead.phone or lead.mobile,
                lead=lead,
                name=lead.name,
            )
        for partner in self.partner_ids:
            add(
                email=partner.email,
                phone=partner.phone or partner.mobile,
                partner=partner,
                name=partner.name,
            )
        for line in (self.emails_manuels or "").splitlines():
            line = line.strip()
            if "@" in line:
                add(email=line)
            elif line:
                add(phone=line)
        for line in (self.phones_manuels or "").splitlines():
            line = line.strip()
            if line:
                add(phone=line)
        return out

    def action_adapter_par_canal(self):
        self.ensure_one()
        from odoo.addons.doorway_messaging.services.claude_service import (
            ClaudeMessagingService,
        )

        canaux = self._active_canaux()
        if not canaux:
            raise UserError(_("Activez au moins un canal."))
        master = _strip_html(self.corps_master) or (self.corps_master or "")
        svc = ClaudeMessagingService(self.env)
        adaptations = svc.adapter_contenu_multicanal(master, canaux)
        vals = {}
        if "email" in adaptations:
            vals["corps_email"] = adaptations["email"]
        if "sms" in adaptations:
            vals["corps_sms"] = adaptations["sms"][:160]
        if "whatsapp" in adaptations:
            vals["corps_whatsapp"] = adaptations["whatsapp"]
        if "linkedin" in adaptations:
            vals["corps_linkedin"] = adaptations["linkedin"]
        if "gmb" in adaptations:
            vals["corps_gmb"] = adaptations["gmb"]
        if self.canal_email and not self.sujet:
            vals["sujet"] = svc.generer_sujet_email(master)
        self.write(vals)
        return True

    def action_apercu(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.message.campaign",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_envoyer(self):
        for campaign in self:
            campaign._send_all()
        return True

    def action_planifier(self):
        self.ensure_one()
        if not self.date_planned:
            raise UserError(_("Indiquez une date d'envoi planifiée."))
        self.write({"statut": "planifie", "envoi_immediat": False})
        return True

    def _send_all(self):
        self.ensure_one()
        self.write({"statut": "en_cours"})
        recipients = self._collect_recipients()
        ok_count, err_count = 0, 0

        if self.canal_email:
            ok, err = self._dispatch_email(recipients)
            ok_count += ok
            err_count += err
        if self.canal_sms:
            ok, err = self._dispatch_sms(recipients)
            ok_count += ok
            err_count += err
        if self.canal_whatsapp:
            ok, err = self._dispatch_whatsapp(recipients)
            ok_count += ok
            err_count += err
        if self.canal_linkedin:
            ok, err = self._dispatch_linkedin()
            ok_count += ok
            err_count += err
        if self.canal_gmb:
            ok, err = self._dispatch_gmb()
            ok_count += ok
            err_count += err

        statut = "termine"
        if err_count and ok_count:
            statut = "erreur"
        elif err_count and not ok_count:
            statut = "erreur"
        self.write(
            {
                "nb_envoyes": ok_count,
                "nb_erreurs": err_count,
                "statut": statut,
            }
        )

    def _create_log(self, canal, destinataire, statut, **kw):
        return self.env["doorway.message.log"].create(
            {
                "campaign_id": self.id,
                "canal": canal,
                "destinataire": destinataire,
                "statut": statut,
                "date_envoi": fields.Datetime.now(),
                **kw,
            }
        )

    def _dispatch_email(self, recipients):
        from odoo.addons.doorway_messaging.services.email_service import EmailService

        svc = EmailService(self.env)
        body = self.corps_email or self.corps_master or ""
        subject = self.sujet or self.name
        ok = err = 0
        for rec in recipients:
            if not rec["email"]:
                continue
            result = svc.send_email(rec["email"], subject, body, rec.get("name"))
            if result.get("success"):
                self._create_log(
                    "email",
                    rec["email"],
                    "envoye",
                    lead_id=rec.get("lead_id"),
                    partner_id=rec.get("partner_id"),
                    message_id=result.get("mail_id", ""),
                    corps_envoye=_strip_html(body)[:2000],
                )
                ok += 1
            else:
                self._create_log(
                    "email",
                    rec["email"],
                    "erreur",
                    lead_id=rec.get("lead_id"),
                    partner_id=rec.get("partner_id"),
                    erreur_msg=result.get("error", ""),
                )
                err += 1
        return ok, err

    def _dispatch_sms(self, recipients):
        from odoo.addons.doorway_messaging.services.sms_service import SmsService

        svc = SmsService(self.env)
        tmpl = self.sms_template_id
        body = (self.corps_sms or _strip_html(self.corps_master) or "")[:1600]
        ok = err = 0
        for rec in recipients:
            if not rec["phone"]:
                continue
            if tmpl and tmpl.twilio_content_sid:
                variables = tmpl.build_content_variables(rec)
                result = svc.send_sms(
                    rec["phone"],
                    body=body or tmpl.corps_text,
                    content_sid=tmpl.twilio_content_sid,
                    content_variables=variables,
                    messaging_service_sid=tmpl.twilio_messaging_service_sid or None,
                )
                corps_envoye = "[template %s] %s" % (
                    tmpl.twilio_content_sid,
                    json.dumps(variables, ensure_ascii=False),
                )
            else:
                result = svc.send_sms(rec["phone"], body=body)
                corps_envoye = body
            if result.get("success"):
                self._create_log(
                    "sms",
                    rec["phone"],
                    "envoye",
                    lead_id=rec.get("lead_id"),
                    partner_id=rec.get("partner_id"),
                    message_id=result.get("sid", ""),
                    corps_envoye=corps_envoye,
                )
                ok += 1
            else:
                self._create_log(
                    "sms",
                    rec["phone"],
                    "erreur",
                    lead_id=rec.get("lead_id"),
                    partner_id=rec.get("partner_id"),
                    erreur_msg=result.get("error", ""),
                )
                err += 1
        return ok, err

    def _dispatch_whatsapp(self, recipients):
        from odoo.addons.doorway_messaging.services.whatsapp_service import (
            WhatsAppService,
        )

        svc = WhatsAppService(self.env)
        tmpl = self.whatsapp_template_id
        body = self.corps_whatsapp or _strip_html(self.corps_master) or ""
        ok = err = 0
        for rec in recipients:
            if not rec["phone"]:
                continue
            if tmpl and tmpl.twilio_content_sid:
                variables = tmpl.build_content_variables(rec)
                result = svc.send_whatsapp(
                    rec["phone"],
                    body=body or tmpl.corps_text,
                    content_sid=tmpl.twilio_content_sid,
                    content_variables=variables,
                    messaging_service_sid=tmpl.twilio_messaging_service_sid or None,
                )
                corps_envoye = "[template %s] %s" % (
                    tmpl.twilio_content_sid,
                    json.dumps(variables, ensure_ascii=False),
                )
            else:
                result = svc.send_whatsapp(rec["phone"], body=body)
                corps_envoye = body[:2000]
            if result.get("success"):
                self._create_log(
                    "whatsapp",
                    rec["phone"],
                    "envoye",
                    lead_id=rec.get("lead_id"),
                    partner_id=rec.get("partner_id"),
                    message_id=result.get("sid", ""),
                    corps_envoye=corps_envoye,
                )
                ok += 1
            else:
                self._create_log(
                    "whatsapp",
                    rec["phone"],
                    "erreur",
                    lead_id=rec.get("lead_id"),
                    partner_id=rec.get("partner_id"),
                    erreur_msg=result.get("error", ""),
                )
                err += 1
        return ok, err

    def _dispatch_linkedin(self):
        from odoo.addons.doorway_messaging.services.linkedin_service import (
            LinkedInService,
        )

        cfg = self.linkedin_page_id
        if not cfg or not cfg.access_token:
            self._create_log(
                "linkedin",
                cfg.name if cfg else "LinkedIn",
                "erreur",
                erreur_msg="Token LinkedIn manquant",
            )
            return 0, 1
        cfg._refresh_token_if_needed()
        texte = self.corps_linkedin or _strip_html(self.corps_master) or ""
        org = (cfg.linkedin_org_id or "").replace("urn:li:organization:", "")
        person = (cfg.linkedin_person_id or "").replace("urn:li:person:", "")
        svc = LinkedInService(cfg.access_token, org_id=org, person_id=person)
        if self.linkedin_type == "personal" and person:
            result = svc.publier_post_personnel(texte)
        else:
            result = svc.publier_post_entreprise(texte)
        if result.get("success"):
            self._create_log(
                "linkedin",
                cfg.name,
                "envoye",
                message_id=result.get("post_id", ""),
                corps_envoye=texte[:3000],
            )
            return 1, 0
        self._create_log(
            "linkedin",
            cfg.name,
            "erreur",
            erreur_msg=result.get("error", ""),
        )
        return 0, 1

    def _dispatch_gmb(self):
        from odoo.addons.doorway_messaging.services.gmb_service import GMBService

        cfg = self.gmb_location_id
        if not cfg or not cfg.access_token:
            self._create_log(
                "gmb",
                cfg.name if cfg else "GMB",
                "erreur",
                erreur_msg="Token GMB manquant",
            )
            return 0, 1
        cfg._refresh_token_if_needed()
        texte = self.corps_gmb or _strip_html(self.corps_master) or ""
        svc = GMBService(
            cfg.access_token, cfg.gmb_account_id or "", cfg.gmb_location_id or ""
        )
        result = svc.creer_post(texte, type_post=self.gmb_post_type or "STANDARD")
        if result.get("success"):
            self._create_log(
                "gmb",
                cfg.gmb_location_name or cfg.name,
                "envoye",
                message_id=result.get("post_name", ""),
                corps_envoye=texte[:1500],
            )
            return 1, 0
        self._create_log(
            "gmb",
            cfg.name,
            "erreur",
            erreur_msg=result.get("error", ""),
        )
        return 0, 1

    @api.model
    def cron_send_planned(self):
        now = fields.Datetime.now()
        campaigns = self.search(
            [
                ("statut", "=", "planifie"),
                ("date_planned", "<=", now),
                ("envoi_immediat", "=", False),
            ]
        )
        for camp in campaigns:
            try:
                camp.action_envoyer()
            except Exception as exc:  # noqa: BLE001
                _logger.exception("cron_send_planned %s: %s", camp.id, exc)
                camp.write({"statut": "erreur"})
