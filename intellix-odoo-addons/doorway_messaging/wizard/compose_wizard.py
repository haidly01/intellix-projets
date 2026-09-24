# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayComposeWizard(models.TransientModel):
    _name = "doorway.compose.wizard"
    _description = "Wizard composition message multi-canal"

    etape = fields.Integer(default=1)

    name = fields.Char("Nom de la campagne", required=True)
    corps_master = fields.Html(
        "Message principal",
        required=True,
        help="Rédigez ici — Claude adaptera pour chaque canal",
    )
    sujet_email = fields.Char("Sujet email")

    corps_email = fields.Html("Version Email")
    corps_sms = fields.Text("Version SMS")
    corps_whatsapp = fields.Text("Version WhatsApp")
    corps_linkedin = fields.Text("Version LinkedIn")
    corps_gmb = fields.Text("Version GMB")

    canal_email = fields.Boolean("Email")
    canal_sms = fields.Boolean("SMS")
    canal_whatsapp = fields.Boolean("WhatsApp")
    canal_linkedin = fields.Boolean("LinkedIn")
    canal_gmb = fields.Boolean("Google My Business")

    source_destinataires = fields.Selection(
        [
            ("leads", "Leads CRM sélectionnés"),
            ("contacts", "Contacts Odoo"),
            ("pipeline", "Tout un pipeline CRM"),
            ("manuel", "Liste manuelle"),
            ("linkedin_only", "Publication LinkedIn (pas de destinataire)"),
            ("gmb_only", "Publication GMB (pas de destinataire)"),
        ],
        default="leads",
    )

    lead_ids = fields.Many2many(
        "crm.lead",
        "doorway_compose_wizard_lead_rel",
        "wizard_id",
        "lead_id",
        string="Leads",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "doorway_compose_wizard_partner_rel",
        "wizard_id",
        "partner_id",
        string="Contacts",
    )
    pipeline_id = fields.Many2one("crm.team", string="Pipeline")
    stage_ids = fields.Many2many(
        "crm.stage",
        "doorway_compose_wizard_stage_rel",
        "wizard_id",
        "stage_id",
        string="Étapes (filtrer)",
    )
    liste_manuelle = fields.Text("Emails / Téléphones (un par ligne)")

    linkedin_page_id = fields.Many2one(
        "doorway.channel.config",
        domain=[("canal", "=", "linkedin"), ("actif", "=", True)],
        string="Config LinkedIn",
    )
    linkedin_type = fields.Selection(
        [("personal", "Profil personnel"), ("company", "Page entreprise")],
        default="company",
    )
    gmb_location_id = fields.Many2one(
        "doorway.channel.config",
        domain=[("canal", "=", "gmb"), ("actif", "=", True)],
        string="Config GMB",
    )
    gmb_post_type = fields.Selection(
        [
            ("STANDARD", "Post standard"),
            ("EVENT", "Événement"),
            ("OFFER", "Offre"),
        ],
        default="STANDARD",
    )

    envoi_immediat = fields.Boolean("Envoyer maintenant", default=True)
    date_planned = fields.Datetime("Planifier pour")

    nb_destinataires_est = fields.Integer(
        "Destinataires estimés", compute="_compute_nb_dest"
    )

    @api.onchange("linkedin_page_id")
    def _onchange_linkedin_page_id(self):
        if self.linkedin_page_id:
            ptype = self.linkedin_page_id.linkedin_profile_type
            self.linkedin_type = (
                "personal" if ptype == "personal" else "company"
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids") or []
        if active_model == "crm.lead" and active_ids:
            res["lead_ids"] = [(6, 0, active_ids)]
            res["source_destinataires"] = "leads"
        elif active_model == "res.partner" and active_ids:
            res["partner_ids"] = [(6, 0, active_ids)]
            res["source_destinataires"] = "contacts"
        return res

    @api.depends(
        "source_destinataires",
        "lead_ids",
        "partner_ids",
        "pipeline_id",
        "stage_ids",
        "liste_manuelle",
        "canal_linkedin",
        "canal_gmb",
    )
    def _compute_nb_dest(self):
        for wiz in self:
            wiz.nb_destinataires_est = len(wiz._preview_recipients())

    def _preview_recipients(self):
        self.ensure_one()
        emails, phones = set(), set()
        if self.source_destinataires in ("linkedin_only", "gmb_only"):
            return []
        if self.source_destinataires == "leads":
            for lead in self.lead_ids:
                if lead.email_from:
                    emails.add(lead.email_from.lower())
                if lead.phone or lead.mobile:
                    phones.add(lead.phone or lead.mobile)
        elif self.source_destinataires == "contacts":
            for p in self.partner_ids:
                if p.email:
                    emails.add(p.email.lower())
                if p.phone or p.mobile:
                    phones.add(p.phone or p.mobile)
        elif self.source_destinataires == "pipeline" and self.pipeline_id:
            domain = [("team_id", "=", self.pipeline_id.id)]
            if self.stage_ids:
                domain.append(("stage_id", "in", self.stage_ids.ids))
            for lead in self.env["crm.lead"].search(domain):
                if lead.email_from:
                    emails.add(lead.email_from.lower())
                if lead.phone or lead.mobile:
                    phones.add(lead.phone or lead.mobile)
        elif self.source_destinataires == "manuel":
            for line in (self.liste_manuelle or "").splitlines():
                line = line.strip()
                if "@" in line:
                    emails.add(line.lower())
                elif line:
                    phones.add(line)
        return list(emails | phones)

    def _active_canaux(self):
        self.ensure_one()
        canaux = []
        for c in ("email", "sms", "whatsapp", "linkedin", "gmb"):
            if getattr(self, "canal_%s" % c):
                canaux.append(c)
        return canaux

    def action_adapter_claude(self):
        self.ensure_one()
        from odoo.addons.doorway_messaging.services.claude_service import (
            ClaudeMessagingService,
        )

        canaux = self._active_canaux()
        if not canaux:
            raise UserError(_("Sélectionnez au moins un canal."))
        master = re.sub(r"<[^>]+>", " ", self.corps_master or "")
        svc = ClaudeMessagingService(self.env)
        adaptations = svc.adapter_contenu_multicanal(master, canaux)
        vals = {"etape": 2}
        for canal, texte in adaptations.items():
            field = "corps_%s" % canal
            if canal == "email":
                vals[field] = texte
            else:
                vals[field] = texte[:3000]
        if self.canal_email and not self.sujet_email:
            vals["sujet_email"] = svc.generer_sujet_email(master)
        self.write(vals)
        return self._reopen()

    def action_etape_suivante(self):
        self.ensure_one()
        if self.etape == 1 and not self._active_canaux():
            raise UserError(_("Sélectionnez au moins un canal."))
        self.etape = min(3, self.etape + 1)
        return self._reopen()

    def action_etape_precedente(self):
        self.etape = max(1, self.etape - 1)
        return self._reopen()

    def _build_campaign_vals(self):
        self.ensure_one()
        emails_manuels = []
        phones_manuels = []
        lead_ids = list(self.lead_ids.ids)
        partner_ids = list(self.partner_ids.ids)

        if self.source_destinataires == "pipeline" and self.pipeline_id:
            domain = [("team_id", "=", self.pipeline_id.id)]
            if self.stage_ids:
                domain.append(("stage_id", "in", self.stage_ids.ids))
            lead_ids = self.env["crm.lead"].search(domain).ids
        elif self.source_destinataires == "manuel":
            for line in (self.liste_manuelle or "").splitlines():
                line = line.strip()
                if "@" in line:
                    emails_manuels.append(line)
                elif line:
                    phones_manuels.append(line)

        return {
            "name": self.name,
            "sujet": self.sujet_email,
            "corps_master": self.corps_master,
            "corps_email": self.corps_email,
            "corps_sms": self.corps_sms,
            "corps_whatsapp": self.corps_whatsapp,
            "corps_linkedin": self.corps_linkedin,
            "corps_gmb": self.corps_gmb,
            "canal_email": self.canal_email,
            "canal_sms": self.canal_sms,
            "canal_whatsapp": self.canal_whatsapp,
            "canal_linkedin": self.canal_linkedin,
            "canal_gmb": self.canal_gmb,
            "lead_ids": [(6, 0, lead_ids)],
            "partner_ids": [(6, 0, partner_ids)],
            "emails_manuels": "\n".join(emails_manuels),
            "phones_manuels": "\n".join(phones_manuels),
            "envoi_immediat": self.envoi_immediat,
            "date_planned": self.date_planned,
            "linkedin_page_id": self.linkedin_page_id.id,
            "linkedin_type": self.linkedin_type,
            "gmb_location_id": self.gmb_location_id.id,
            "gmb_post_type": self.gmb_post_type,
            "statut": "en_cours" if self.envoi_immediat else "planifie",
        }

    def action_envoyer(self):
        self.ensure_one()
        campaign = self.env["doorway.message.campaign"].create(
            self._build_campaign_vals()
        )
        if self.envoi_immediat:
            campaign.action_envoyer()
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.message.campaign",
            "res_id": campaign.id,
            "view_mode": "form",
            "target": "current",
        }

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.compose.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
