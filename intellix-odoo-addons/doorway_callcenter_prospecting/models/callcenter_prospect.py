# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REQUIRED_TAGS = [
    "Prospect Call Center",
    "Maroc",
    "Tunisie",
    "WhatsApp OK",
    "Landline",
    "Téléphone seulement",
    "Qualifié Démo",
    "NI – Call Center",
]

STAGE_NAMES = [
    "Nouveau",
    "Contacté J0",
    "Contacté J2",
    "Dernier Contact",
    "Qualifié Démo",
    "Démo Planifiée",
    "Démo Faite",
    "NI",
]


class DoorwayCallcenterProspect(models.Model):
    _name = "doorway.callcenter.prospect"
    _description = "Prospect call center MA/TN"
    _order = "create_date desc"
    _rec_name = "company_name"

    company_name = fields.Char(required=True, index=True)
    phone = fields.Char(required=True, index=True)
    phone_raw = fields.Char()
    whatsapp = fields.Char()
    email = fields.Char()
    city = fields.Char()
    country = fields.Selection([("MA", "Maroc"), ("TN", "Tunisie")], required=True)
    source = fields.Char()
    website = fields.Char()
    contact_name = fields.Char()
    estimated_agents = fields.Char()
    notes = fields.Text()
    extracted_at = fields.Datetime(default=fields.Datetime.now)

    twilio_valid = fields.Boolean()
    line_type = fields.Char()
    carrier = fields.Char()
    whatsapp_capable = fields.Boolean()

    contacted_j0 = fields.Boolean(default=False)
    contacted_j0_at = fields.Datetime()
    contacted_j2 = fields.Boolean(default=False)
    contacted_j2_at = fields.Datetime()
    contacted_j5 = fields.Boolean(default=False)
    contacted_j5_at = fields.Datetime()
    last_reply = fields.Text()
    last_reply_at = fields.Datetime()
    reply_intent = fields.Selection(
        [
            ("INTERESTED", "Intéressé"),
            ("NOT_INTERESTED", "Pas intéressé"),
            ("QUESTION", "Question"),
            ("SCHEDULE", "Planifier"),
            ("OTHER", "Autre"),
        ]
    )

    crm_lead_id = fields.Many2one("crm.lead", string="Lead CRM", ondelete="set null")
    status = fields.Selection(
        [
            ("NEW", "Nouveau"),
            ("LANDLINE", "Landline — agent IA"),
            ("CONTACTED", "Contacté"),
            ("QUALIFIED", "Qualifié"),
            ("NI", "Non intéressé"),
            ("DNC", "STOP / DNC"),
        ],
        default="NEW",
        index=True,
    )
    demo_scheduled_at = fields.Datetime()
    extraction_campaign_id = fields.Many2one("doorway.campagne.extraction")

    _phone_uniq = models.Constraint(
        "unique(phone)",
        "Ce numéro existe déjà.",
    )

    @api.model
    def _ensure_marketing_tags(self):
        Tag = self.env["crm.tag"].sudo()
        for name in REQUIRED_TAGS:
            if not Tag.search([("name", "=", name)], limit=1):
                Tag.create({"name": name})

    @api.model
    def _tag_id(self, name):
        self._ensure_marketing_tags()
        tag = self.env["crm.tag"].sudo().search([("name", "=", name)], limit=1)
        return tag.id if tag else False

    @api.model
    def _marketing_team(self):
        return self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )

    @api.model
    def _stage_id(self, stage_name):
        team = self._marketing_team()
        if not team:
            return False
        stage = self.env["crm.stage"].sudo().search(
            [("name", "=", stage_name), ("team_ids", "in", team.id)],
            limit=1,
        )
        return stage.id if stage else False

    @api.model
    def _resolve_assignee(self):
        config = self.env["doorway.credit.config"].sudo().get_config()
        login = (config.crm_assignee_login or "zakaria@agencedoorway.com").strip()
        user = self.env["res.users"].sudo().search(
            [("login", "=", login), ("active", "=", True)], limit=1
        )
        if user:
            return user
        team = self._marketing_team()
        return team._get_default_assignee() if team else self.env["res.users"]

    @api.model
    def ingest_from_dict(self, payload):
        """Importe un prospect (extraction n8n / API)."""
        country = (payload.get("country") or "MA").upper()
        from odoo.addons.doorway_callcenter_prospecting.services.phone_normalize import (
            normalize_phone_e164,
        )

        phone_raw = payload.get("phone_raw") or payload.get("phone") or ""
        phone = normalize_phone_e164(phone_raw, country)
        if not phone:
            return {"ok": False, "error": "Numéro invalide", "phone_raw": phone_raw}

        existing = self.search([("phone", "=", phone)], limit=1)
        if existing:
            return {"ok": True, "id": existing.id, "duplicate": True}

        company = (payload.get("company_name") or "").strip()
        if not company or len(company) < 2:
            return {"ok": False, "error": "Nom entreprise requis"}

        rec = self.create(
            {
                "company_name": company[:200],
                "phone": phone,
                "phone_raw": phone_raw,
                "whatsapp": payload.get("whatsapp"),
                "email": payload.get("email"),
                "city": payload.get("city"),
                "country": country if country in ("MA", "TN") else "MA",
                "source": payload.get("source"),
                "website": payload.get("website"),
                "contact_name": payload.get("contact_name"),
                "estimated_agents": payload.get("estimated_agents"),
                "notes": payload.get("notes"),
            }
        )
        return {"ok": True, "id": rec.id, "duplicate": False}

    def _is_landline(self):
        self.ensure_one()
        return (self.line_type or "").lower() == "landline"

    def action_validate_twilio(self):
        from odoo.addons.doorway_callcenter_prospecting.services.twilio_lookup import (
            TwilioLookupService,
        )

        svc = TwilioLookupService(self.env)
        for rec in self:
            result = svc.lookup_phone(rec.phone)
            rec.write(
                {
                    "twilio_valid": result.get("valid"),
                    "line_type": result.get("line_type"),
                    "carrier": result.get("carrier"),
                    "whatsapp_capable": result.get("whatsapp_capable"),
                }
            )
            if not result.get("valid"):
                rec.status = "NI"
            elif rec._is_landline():
                rec.status = "LANDLINE"
                if not rec.crm_lead_id:
                    rec._create_crm_lead()
            elif result.get("whatsapp_capable") and not rec.crm_lead_id:
                rec._create_crm_lead()
        return True

    def _create_crm_lead(self):
        team = self._marketing_team()
        if not team:
            raise UserError(_("Pipeline Marketing introuvable."))
        assignee = self._resolve_assignee()
        country_rec = self.env["res.country"].sudo().search(
            [("code", "=", self.country)], limit=1
        )
        tag_ids = [self._tag_id("Prospect Call Center")]
        if self.country == "MA":
            tag_ids.append(self._tag_id("Maroc"))
        else:
            tag_ids.append(self._tag_id("Tunisie"))
        if self._is_landline():
            tag_ids.append(self._tag_id("Landline"))
        elif self.whatsapp_capable:
            tag_ids.append(self._tag_id("WhatsApp OK"))

        stage_id = self._stage_id("Nouveau")
        vals = {
            "name": "Call Center – %s (%s)" % (self.company_name, self.country),
            "type": "opportunity",
            "team_id": team.id,
            "stage_id": stage_id or False,
            "contact_name": self.contact_name or self.company_name,
            "phone": self.phone,
            "email_from": self.email or False,
            "website": self.website or False,
            "city": self.city or False,
            "tag_ids": [(6, 0, [t for t in tag_ids if t])],
            "description": "Source: %s\nExtrait: %s" % (self.source or "-", self.extracted_at),
            "lead_provenance": "nouveau",
        }
        if assignee:
            vals["user_id"] = assignee.id
        if country_rec:
            vals["country_id"] = country_rec.id
        lead = self.env["crm.lead"].sudo().create(vals)
        self.crm_lead_id = lead.id
        return lead

    def _send_whatsapp_template(self, sequence="j0", extra_vars=None):
        """WhatsApp via Twilio ContentSid — mobile uniquement."""
        self.ensure_one()
        if not self.whatsapp_capable:
            return {
                "success": False,
                "skipped": True,
                "error": "Landline ou non-mobile — WhatsApp ignoré",
            }
        from odoo.addons.doorway_callcenter_prospecting.services.twilio_whatsapp import (
            TwilioWhatsAppService,
        )

        name = self.contact_name or self.company_name
        return TwilioWhatsAppService(self.env).send_sequence(
            self.phone, sequence, name, extra_vars=extra_vars
        )

    def _send_whatsapp_reply(self, body):
        """Réponse session 24h après message entrant prospect."""
        self.ensure_one()
        from odoo.addons.doorway_callcenter_prospecting.services.twilio_whatsapp import (
            TwilioWhatsAppService,
        )

        return TwilioWhatsAppService(self.env).send_session_text(self.phone, body)

    def action_send_j0(self):
        sent = 0
        for rec in self.filtered(
            lambda r: r.status == "NEW"
            and not r.contacted_j0
            and r.whatsapp_capable
            and r.twilio_valid
        ):
            if not rec.crm_lead_id:
                rec._create_crm_lead()
            result = rec._send_whatsapp_template("j0")
            if result.get("success"):
                sent += 1
                rec.write(
                    {
                        "contacted_j0": True,
                        "contacted_j0_at": fields.Datetime.now(),
                        "status": "CONTACTED",
                    }
                )
                if rec.crm_lead_id:
                    stage = rec._stage_id("Contacté J0")
                    if stage:
                        rec.crm_lead_id.stage_id = stage
        return sent

    def action_send_j2(self):
        cutoff = fields.Datetime.now() - timedelta(days=2)
        domain = [
            ("contacted_j0", "=", True),
            ("contacted_j2", "=", False),
            ("contacted_j0_at", "<=", cutoff),
            ("reply_intent", "=", False),
            ("status", "=", "CONTACTED"),
        ]
        for rec in self.search(domain).filtered("whatsapp_capable"):
            result = rec._send_whatsapp_template("j2")
            if result.get("success"):
                rec.write(
                    {"contacted_j2": True, "contacted_j2_at": fields.Datetime.now()}
                )
                stage = rec._stage_id("Contacté J2")
                if stage and rec.crm_lead_id:
                    rec.crm_lead_id.stage_id = stage
        return True

    def action_send_j5(self):
        cutoff = fields.Datetime.now() - timedelta(days=3)
        domain = [
            ("contacted_j2", "=", True),
            ("contacted_j5", "=", False),
            ("contacted_j2_at", "<=", cutoff),
            ("reply_intent", "=", False),
            ("status", "=", "CONTACTED"),
        ]
        for rec in self.search(domain).filtered("whatsapp_capable"):
            result = rec._send_whatsapp_template("j5")
            if result.get("success"):
                rec.write(
                    {"contacted_j5": True, "contacted_j5_at": fields.Datetime.now()}
                )
                stage = rec._stage_id("Dernier Contact")
                if stage and rec.crm_lead_id:
                    rec.crm_lead_id.stage_id = stage
        return True

    @api.model
    def process_incoming_reply(self, phone, body, profile_name=None):
        """Traite une réponse WhatsApp/SMS entrante."""
        from odoo.addons.doorway_callcenter_prospecting.services.phone_normalize import (
            normalize_phone_e164,
        )
        from odoo.addons.doorway_callcenter_prospecting.services.message_templates import (
            message_qualified_demo,
        )

        digits = (phone or "").replace("whatsapp:", "").strip()
        prospect = self.search([("phone", "=", digits)], limit=1)
        if not prospect and digits.startswith("+"):
            for cc in ("MA", "TN"):
                norm = normalize_phone_e164(digits, cc)
                if norm:
                    prospect = self.search([("phone", "=", norm)], limit=1)
                    if prospect:
                        break

        if not prospect:
            return {"ok": False, "error": "Prospect introuvable"}

        text = (body or "").strip().upper()
        if text in ("STOP", "ARRET", "ARRÊT", "DESABONNER"):
            prospect.write({"status": "DNC", "last_reply": body, "last_reply_at": fields.Datetime.now()})
            return {"ok": True, "intent": "DNC"}

        intent = "OTHER"
        qualify = False
        if any(k in text for k in ("OUI", "YES", "OK", "INTERESSE", "INTÉRESSÉ", "DEMO", "DÉMO")):
            intent, qualify = "INTERESTED", True
        elif any(k in text for k in ("NON", "NO", "PAS INTERESSE", "PAS INTÉRESSÉ")):
            intent, qualify = "NOT_INTERESTED", False

        prospect.write(
            {
                "last_reply": body,
                "last_reply_at": fields.Datetime.now(),
                "reply_intent": intent,
                "status": "QUALIFIED" if qualify else prospect.status,
            }
        )
        if intent == "NOT_INTERESTED":
            prospect.status = "NI"
            tag_ni = prospect._tag_id("NI – Call Center")
            if prospect.crm_lead_id and tag_ni:
                prospect.crm_lead_id.write({"tag_ids": [(4, tag_ni)]})
            stage = prospect._stage_id("NI")
            if stage and prospect.crm_lead_id:
                prospect.crm_lead_id.stage_id = stage
            return {"ok": True, "intent": intent, "qualify": False}

        if qualify:
            tag_q = prospect._tag_id("Qualifié Démo")
            stage = prospect._stage_id("Qualifié Démo")
            if not prospect.crm_lead_id:
                prospect._create_crm_lead()
            if prospect.crm_lead_id:
                if tag_q:
                    prospect.crm_lead_id.write({"tag_ids": [(4, tag_q)]})
                if stage:
                    prospect.crm_lead_id.stage_id = stage
            icp = self.env["ir.config_parameter"].sudo()
            booking = icp.get_param("doorway_callcenter_prospecting.demo_booking_url", "")
            reply = message_qualified_demo(booking, profile_name or prospect.contact_name)
            send = prospect._send_whatsapp_reply(reply)
            return {"ok": True, "intent": intent, "qualify": True, "sent": send.get("success")}

        return {"ok": True, "intent": intent, "qualify": False}

    @api.model
    def import_from_leads_bruts(self, campagne_id, limit=500):
        """Convertit les leads bruts d'une campagne extraction en prospects."""
        Leads = self.env["doorway.leads.bruts"].sudo()
        campagne = self.env["doorway.campagne.extraction"].browse(campagne_id)
        if not campagne.exists():
            return {"ok": False, "error": "Campagne introuvable"}
        zone = campagne.zone_geographique or "maroc"
        country = "TN" if zone == "tunisie" else "MA"
        leads = Leads.search(
            [("campagne_id", "=", campagne.id), ("phone", "!=", False)],
            limit=limit,
        )
        created = 0
        dupes = 0
        invalid = 0
        for lb in leads:
            res = self.ingest_from_dict(
                {
                    "company_name": lb.name,
                    "phone_raw": lb.phone,
                    "email": lb.email,
                    "city": lb.city,
                    "country": country,
                    "source": lb.source_id.name or lb.source_key,
                    "website": lb.website,
                    "notes": lb.notes,
                }
            )
            if res.get("duplicate"):
                dupes += 1
            elif res.get("ok"):
                created += 1
                rec = self.browse(res["id"])
                rec.extraction_campaign_id = campagne.id
            else:
                invalid += 1
        return {"ok": True, "created": created, "dupes": dupes, "invalid": invalid}

    def action_prospect_phone_call(self):
        self.ensure_one()
        phone = (self.phone or self.phone_raw or "").strip()
        if not phone:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Téléphone",
                    "message": "Aucun numéro sur cette fiche.",
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "vicidial_workstation_action",
            "params": {"doorway_vicidial_dial_phone": phone},
        }

