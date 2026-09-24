# -*- coding: utf-8 -*-
import base64
import logging
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

WIZARD_STEPS = (
    "identity",
    "voice",
    "latency",
    "prompt",
    "actions",
    "library",
    "telephony",
)

ACTION_CODE_MAP = {
    "create_lead": "allow_create_lead",
    "send_sms": "allow_send_sms",
    "human_transfer": "allow_human_transfer",
    "lead_note": "allow_lead_note",
    "n8n_workflow": "allow_n8n_workflow",
    "send_email": "allow_send_email",
}


class AgentProfileWizard(models.Model):
    _inherit = "doorway.agent.profile"

    wizard_step = fields.Selection(
        [
            ("identity", "1 — Identité"),
            ("voice", "2 — Voix"),
            ("latency", "3 — Latence"),
            ("prompt", "4 — Prompt"),
            ("actions", "5 — Actions"),
            ("library", "6 — Bibliothèque"),
            ("telephony", "7 — Téléphonie"),
            ("summary", "Récapitulatif"),
        ],
        string="Étape wizard",
        default="identity",
    )
    wizard_completion_pct = fields.Integer(
        string="Complétion wizard %",
        compute="_compute_wizard_completion_pct",
    )
    voice_id = fields.Char(string="ElevenLabs Voice ID")
    voice_speed = fields.Float(string="Vitesse voix", default=1.0)
    voice_stability = fields.Float(string="Stabilité voix", default=0.5)
    latency_mode = fields.Selection(
        [
            ("low", "Faible latence"),
            ("balanced", "Équilibré"),
            ("quality", "Haute qualité"),
        ],
        string="Mode latence",
        default="balanced",
    )
    action_tag_ids = fields.Many2many(
        "doorway.agent.action.tag",
        "doorway_agent_profile_action_tag_rel",
        "profile_id",
        "tag_id",
        string="Actions activées",
    )
    allow_create_lead = fields.Boolean(string="Action: Créer lead CRM", default=True)
    allow_lead_note = fields.Boolean(string="Action: Note sur lead", default=True)
    allow_n8n_workflow = fields.Boolean(string="Action: Workflow n8n", default=False)
    n8n_webhook_url = fields.Char(string="Webhook n8n")
    is_template = fields.Boolean(string="Template réutilisable", default=False)
    template_name = fields.Char(string="Nom du template")
    template_tag_ids = fields.Many2many(
        "doorway.agent.template.tag",
        "doorway_agent_profile_template_tag_rel",
        "profile_id",
        "tag_id",
        string="Tags template",
    )
    source_template_id = fields.Many2one(
        "doorway.agent.profile",
        string="Template source",
        domain="[('is_template', '=', True)]",
    )

    @api.depends("wizard_step", "name", "voice_id", "system_prompt", "action_tag_ids")
    def _compute_wizard_completion_pct(self):
        weights = {
            "identity": 12,
            "voice": 12,
            "latency": 8,
            "prompt": 22,
            "actions": 12,
            "library": 8,
            "telephony": 12,
            "summary": 8,
        }
        order = list(WIZARD_STEPS) + ["summary"]
        for rec in self:
            step = rec.wizard_step or "identity"
            idx = order.index(step) if step in order else 0
            base = sum(weights[s] for s in order[: idx + 1])
            bonus = 0
            if rec.name:
                bonus += 2
            if rec.voice_id:
                bonus += 3
            if rec.system_prompt:
                bonus += 5
            rec.wizard_completion_pct = min(100, base + bonus)

    @api.model
    def _draft_external_id(self):
        return "draft-%s" % uuid.uuid4().hex[:16]

    @api.model
    def wizard_create_draft(self, template_id=None):
        """Crée un brouillon d'agent pour le wizard OWL."""
        vals = {
            "name": _("Nouvel agent"),
            "provider": "elevenlabs",
            "external_agent_id": self._draft_external_id(),
            "status": "inactive",
            "wizard_step": "identity",
            "pipeline": "doorway",
            "agent_type": "inbound",
            "language": "fr",
        }
        if template_id:
            template = self.browse(template_id).exists()
            if template and template.is_template:
                vals.update(
                    template._wizard_export_vals(),
                )
                vals["source_template_id"] = template.id
                vals["external_agent_id"] = self._draft_external_id()
                vals["status"] = "inactive"
                vals["wizard_step"] = "identity"
        return self.create(vals).id

    def _wizard_export_vals(self):
        self.ensure_one()
        return {
            "name": self.name,
            "pipeline": self.pipeline,
            "agent_type": self.agent_type,
            "language": self.language,
            "voice_id": self.voice_id,
            "voice_clone_id": self.voice_clone_id,
            "voice_name": self.voice_name,
            "voice_gender": self.voice_gender,
            "voice_speed": self.voice_speed,
            "voice_stability": self.voice_stability,
            "export_calls_google_sheet": self.export_calls_google_sheet,
            "google_sheets_spreadsheet_id": self.google_sheets_spreadsheet_id,
            "latency_mode": self.latency_mode,
            "latency_target_ms": self.latency_target_ms,
            "system_prompt": self.system_prompt,
            "action_tag_ids": [(6, 0, self.action_tag_ids.ids)],
            "allow_create_lead": self.allow_create_lead,
            "allow_send_sms": self.allow_send_sms,
            "allow_send_email": self.allow_send_email,
            "allow_human_transfer": self.allow_human_transfer,
            "allow_lead_note": self.allow_lead_note,
            "allow_n8n_workflow": self.allow_n8n_workflow,
            "n8n_webhook_url": self.n8n_webhook_url,
        }

    def _sync_action_booleans(self, tag_codes):
        """Met à jour les booléens d'actions depuis les codes de tags."""
        codes = set(tag_codes or [])
        vals = {field: code in codes for code, field in ACTION_CODE_MAP.items()}
        self.write(vals)

    @api.model
    def wizard_get_config(self, agent_id=None):
        """Configuration initiale du wizard (étapes, variables, actions)."""
        agent = self.browse(agent_id) if agent_id else self.browse()
        actions = self.env["doorway.agent.action.tag"].search_read(
            [("active", "=", True)],
            ["id", "name", "code", "description"],
            order="sequence, name",
        )
        variables = [
            {"key": "prénom", "token": "{{prénom}}"},
            {"key": "pipeline", "token": "{{pipeline}}"},
            {"key": "objectif", "token": "{{objectif}}"},
            {"key": "entreprise", "token": "{{entreprise}}"},
        ]
        pipelines = [
            {"value": "renovation", "label": "Rénovation"},
            {"value": "immobilier", "label": "Immobilier"},
            {"value": "driven", "label": "Finance / Driven"},
            {"value": "assurance", "label": "Assurance"},
            {"value": "doorway", "label": "Doorway Clients"},
        ]
        latency_modes = [
            {"value": "low", "label": "Faible latence", "ms": 400, "hint": "Réponse ~400 ms, légèrement moins naturel."},
            {"value": "balanced", "label": "Équilibré", "ms": 800, "hint": "Bon compromis réactivité / qualité vocale."},
            {"value": "quality", "label": "Haute qualité", "ms": 1200, "hint": "Voix plus naturelle, latence ~1,2 s."},
        ]
        data = {}
        if agent:
            data = agent._wizard_read_payload()
        return {
            "steps": list(WIZARD_STEPS) + ["summary"],
            "actions": actions,
            "variables": variables,
            "pipelines": pipelines,
            "latency_modes": latency_modes,
            "agent": data,
        }

    def _wizard_read_payload(self):
        self.ensure_one()
        prompt_info = self.get_effective_prompt_info()
        system_prompt = (self.system_prompt or "").strip()
        if not system_prompt:
            system_prompt = prompt_info.get("prompt") or ""
        return {
            "id": self.id,
            "name": self.name or "",
            "pipeline": self.pipeline,
            "agent_type": self.agent_type,
            "language": self.language,
            "voice_name": self.voice_name or "",
            "voice_clone_id": self.voice_clone_id or "",
            "has_voice_sample": bool(self.voice_sample_file),
            "voice_sample_filename": self.voice_sample_filename or "",
            "voice_id": self.voice_id or self.voice_clone_id or "",
            "voice_gender": self.voice_gender or "female",
            "voice_speed": self.voice_speed,
            "export_calls_google_sheet": self.export_calls_google_sheet,
            "google_sheets_spreadsheet_id": self.google_sheets_spreadsheet_id or "",
            "voice_stability": self.voice_stability,
            "latency_mode": self.latency_mode or "balanced",
            "system_prompt": system_prompt,
            "prompt_source": prompt_info.get("source") or "own",
            "prompt_linked_name": prompt_info.get("linked_name") or "",
            "prompt_linked_id": prompt_info.get("linked_id") or False,
            "action_tag_ids": self.action_tag_ids.ids,
            "n8n_webhook_url": self.n8n_webhook_url or "",
            "is_template": self.is_template,
            "template_name": self.template_name or "",
            "template_tag_ids": self.template_tag_ids.ids,
            "source_template_id": self.source_template_id.id or False,
            "wizard_step": self.wizard_step or "identity",
            "wizard_completion_pct": self.wizard_completion_pct,
            "status": self.status,
            "is_edit_mode": bool(
                self.external_agent_id
                and not str(self.external_agent_id).startswith("draft-")
            ),
            "telephony": self._wizard_telephony_payload(),
        }

    def _wizard_telephony_payload(self):
        self.ensure_one()
        line = self.default_phone_number_id
        if not line and self.phone_number_ids:
            line = self.phone_number_ids.filtered("is_primary")[:1]
        if not line:
            line = self.phone_number_ids[:1]
        trunk = line.trunk_id if line else False
        return {
            "phone_line_id": line.id if line else False,
            "phone_number": (line.phone_number or "") if line else "",
            "phone_source": (line.phone_source or "manual") if line else "manual",
            "sip_trunk_name": (line.sip_trunk_name or "") if line else "",
            "twilio_sip_trunk_sid": (line.twilio_sip_trunk_sid or "") if line else "",
            "trunk_id": trunk.id if trunk else False,
            "trunk_name": trunk.name if trunk else "",
            "elevenlabs_phone_number_id": (
                (line.elevenlabs_phone_number_id or "") if line else ""
            ),
        }

    def wizard_save_step(self, step, payload=None):
        """Sauvegarde auto à chaque étape."""
        self.ensure_one()
        payload = payload or {}
        vals = {"wizard_step": step}
        field_map = {
            "name": "name",
            "pipeline": "pipeline",
            "agent_type": "agent_type",
            "language": "language",
            "voice_name": "voice_name",
            "voice_id": "voice_id",
            "voice_gender": "voice_gender",
            "voice_speed": "voice_speed",
            "export_calls_google_sheet": "export_calls_google_sheet",
            "google_sheets_spreadsheet_id": "google_sheets_spreadsheet_id",
            "voice_stability": "voice_stability",
            "latency_mode": "latency_mode",
            "system_prompt": "system_prompt",
            "n8n_webhook_url": "n8n_webhook_url",
            "is_template": "is_template",
            "template_name": "template_name",
        }
        for key, field in field_map.items():
            if key in payload:
                vals[field] = payload[key]
        if "action_tag_ids" in payload:
            vals["action_tag_ids"] = [(6, 0, payload["action_tag_ids"] or [])]
        if "template_tag_ids" in payload:
            vals["template_tag_ids"] = [(6, 0, payload["template_tag_ids"] or [])]
        if payload.get("latency_mode"):
            ms_map = {"low": 400, "balanced": 800, "quality": 1200}
            vals["latency_target_ms"] = ms_map.get(payload["latency_mode"], 800)
        if payload.get("voice_id"):
            vals["voice_clone_id"] = payload["voice_id"]
        self.write(vals)
        if "action_tag_ids" in payload:
            tags = self.env["doorway.agent.action.tag"].browse(payload["action_tag_ids"])
            self._sync_action_booleans(tags.mapped("code"))
        if "system_prompt" in payload and (payload.get("system_prompt") or "").strip():
            ext = (self.external_agent_id or "").strip()
            if ext.startswith("agent_"):
                twins = self.search(
                    [
                        ("external_agent_id", "=", ext),
                        ("id", "!=", self.id),
                        ("status", "=", "active"),
                    ]
                )
                if twins:
                    twins.write({"system_prompt": payload["system_prompt"]})
            if step not in ("prompt", "summary"):
                try:
                    sync = self.sync_prompt_to_elevenlabs()
                    if not sync.get("ok"):
                        _logger.warning(
                            "Sync prompt EL wizard (agent %s): %s",
                            self.id,
                            sync.get("message"),
                        )
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("Sync prompt EL wizard %s: %s", self.id, exc)
        return self._wizard_read_payload()

    def wizard_list_voices(self, language=None, gender=None, locale=None):
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        lang = language or self.language or "fr"
        gen = gender or self.voice_gender or "any"
        cloned = None
        vid = (self.voice_clone_id or self.voice_id or "").strip()
        if vid:
            cloned = {
                "voice_id": vid,
                "name": self.voice_name or self.name or _("Ma voix clonée"),
            }
        return ElevenLabsClient(self.env).list_voices_for_wizard(
            lang, cloned, gen, locale=locale or None
        )

    def wizard_upload_voice_sample(self, filename, data_b64):
        """Enregistre l'échantillon audio pour clonage (étape Voix)."""
        self.ensure_one()
        if not data_b64:
            raise UserError(_("Fichier audio vide."))
        try:
            raw = base64.b64decode(data_b64)
        except Exception as exc:  # noqa: BLE001
            raise UserError(_("Fichier audio invalide.")) from exc
        if len(raw) < 1024:
            raise UserError(_("Le fichier audio est trop court (min. ~1 Ko)."))
        self.write(
            {
                "voice_sample_file": data_b64,
                "voice_sample_filename": filename or "voice_sample.m4a",
            }
        )
        return {
            "ok": True,
            "filename": self.voice_sample_filename,
            "has_voice_sample": True,
        }

    def wizard_create_voice_clone(self, voice_name=None):
        """Crée la voix ElevenLabs depuis l'échantillon uploadé."""
        self.ensure_one()
        if not self.voice_sample_file:
            raise UserError(_("Joignez d'abord un échantillon audio (30 s à 2 min)."))
        name = (voice_name or self.voice_name or self.name or _("Voix agent")).strip()
        if not name:
            raise UserError(_("Nom de la voix requis."))

        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        audio_content = base64.b64decode(self.voice_sample_file)
        client = ElevenLabsClient(self.env)
        if not client.is_available():
            raise UserError(_("Clé API ElevenLabs non configurée."))
        try:
            result = client.create_voice_clone(
                name,
                audio_content,
                self.voice_sample_filename or "voice_sample.m4a",
            )
        except Exception as exc:  # noqa: BLE001
            raise UserError(_("Échec clonage voix : %s") % exc) from exc

        voice_id = result.get("voice_id") or ""
        self.write(
            {
                "voice_name": name,
                "voice_clone_id": voice_id,
                "voice_id": voice_id,
                "last_sync": fields.Datetime.now(),
            }
        )
        return {
            "voice_id": voice_id,
            "voice_name": name,
            "voices": self.wizard_list_voices(self.language),
        }

    def wizard_voice_preview(self, voice_id=None, speed=1.0, stability=0.5, language=None):
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        lang = language or self.language or "fr"
        audio_b64 = ElevenLabsClient(self.env).voice_preview_audio(
            voice_id,
            speed=speed,
            stability=stability,
            language=lang,
        )
        return {"audio_base64": audio_b64, "mime": "audio/mpeg"}

    @api.model
    def wizard_test_prompt(self, system_prompt=None, user_message=None):
        from odoo.addons.doorway_agents_dashboard.services.claude_service import (
            ClaudeService,
        )

        svc = ClaudeService(self.env)
        if not svc.is_available():
            raise UserError(_("Clé API Anthropic non configurée."))
        reply = svc.test_agent_prompt(system_prompt or "", user_message or "")
        tokens = max(1, (len(system_prompt or "") + len(user_message or "") + len(reply)) // 4)
        return {"reply": reply, "token_estimate": tokens}

    @api.model
    def wizard_list_templates(self, pipeline=None):
        domain = [("is_template", "=", True)]
        if pipeline:
            domain.append(("pipeline", "=", pipeline))
        rows = self.search_read(
            domain,
            ["id", "name", "template_name", "pipeline", "agent_type", "language"],
            order="name",
        )
        return rows

    def _link_phone_to_elevenlabs(self):
        """Lie le numéro principal à ElevenLabs si l'agent est déployé."""
        self.ensure_one()
        line = self.default_phone_number_id
        if not line:
            return ""
        ext = (self.external_agent_id or "").strip()
        if not ext or ext.startswith("draft-"):
            return ""
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        client = ElevenLabsClient(self.env)
        ph_id = client.ensure_twilio_phone_number(
            line.phone_number,
            agent_id=ext,
            label=self.name,
        )
        line.write({"elevenlabs_phone_number_id": ph_id})
        return ph_id

    def _set_primary_phone_line(self, line):
        self.ensure_one()
        if not line:
            return
        others = self.phone_number_ids.filtered(lambda p: p.id != line.id)
        others.write({"is_primary": False})
        line.write({"is_primary": True, "active": True})
        self.write({"default_phone_number_id": line.id})

    def wizard_get_telephony(self):
        """État téléphonie + inventaire Twilio pour l'étape wizard."""
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.twilio_provision_service import (
            TwilioProvisionService,
        )

        provision = TwilioProvisionService(self.env)
        twilio_ready = provision._twilio.is_available()
        owned = []
        if twilio_ready:
            try:
                owned = provision.list_account_numbers()
            except UserError:
                owned = []
        trunks = self.env["doorway.sip.trunk"].search_read(
            [("active", "=", True)],
            ["id", "name", "provider", "twilio_trunk_sid", "termination_uri"],
            order="name",
        )
        return {
            "telephony": self._wizard_telephony_payload(),
            "twilio_configured": twilio_ready,
            "twilio_owned_numbers": owned,
            "sip_trunks": trunks,
            "countries": [
                {"code": "CA", "label": "Canada"},
                {"code": "US", "label": "États-Unis"},
                {"code": "FR", "label": "France"},
            ],
        }

    @api.model
    def wizard_search_twilio_numbers(self, country="CA", area_code=None):
        from odoo.addons.doorway_agents_dashboard.services.twilio_provision_service import (
            TwilioProvisionService,
        )

        return TwilioProvisionService(self.env).search_available_numbers(
            country=country,
            area_code=area_code,
        )

    def wizard_create_sip_trunk(self, payload=None):
        """Crée un SIP trunk réutilisable (BYOC ou indépendant)."""
        self.ensure_one()
        payload = payload or {}
        name = (payload.get("name") or "").strip()
        if not name:
            raise UserError(_("Nom du SIP trunk requis."))
        trunk = self.env["doorway.sip.trunk"].create(
            {
                "name": name,
                "provider": payload.get("provider") or "twilio",
                "twilio_trunk_sid": (payload.get("twilio_trunk_sid") or "").strip(),
                "termination_uri": (payload.get("termination_uri") or "").strip(),
                "sip_username": (payload.get("sip_username") or "").strip(),
                "notes": (payload.get("notes") or "").strip(),
            }
        )
        return {
            "trunk_id": trunk.id,
            "trunk_name": trunk.name,
            "sip_trunks": self.env["doorway.sip.trunk"].search_read(
                [("active", "=", True)],
                ["id", "name", "provider", "twilio_trunk_sid", "termination_uri"],
                order="name",
            ),
        }

    def wizard_assign_phone(self, mode, payload=None):
        """
        Assigne un numéro à l'agent.
        mode: existing | twilio_owned | twilio_purchase | sip_trunk
        """
        self.ensure_one()
        payload = payload or {}
        from odoo.addons.doorway_agents_dashboard.services.twilio_provision_service import (
            TwilioProvisionService,
        )

        provision = TwilioProvisionService(self.env)
        Phone = self.env["doorway.agent.phone.number"]
        phone_number = ""
        twilio_sid = ""
        phone_source = "manual"
        trunk = False
        sip_trunk_name = ""
        twilio_sip_trunk_sid = ""

        if mode == "twilio_purchase":
            phone_number = payload.get("phone_number")
            if not phone_number:
                raise UserError(_("Sélectionnez un numéro à acheter."))
            purchased = provision.purchase_number(
                phone_number,
                friendly_name=self.name,
            )
            phone_number = purchased["phone_number"]
            twilio_sid = purchased["sid"]
            phone_source = "twilio_purchased"
        elif mode == "twilio_owned":
            phone_number = payload.get("phone_number")
            twilio_sid = (payload.get("twilio_incoming_sid") or "").strip()
            if not phone_number:
                raise UserError(_("Sélectionnez un numéro Twilio existant."))
            phone_number = provision.normalize_e164(phone_number)
            phone_source = "manual"
        elif mode == "sip_trunk":
            phone_number = payload.get("phone_number")
            if not phone_number:
                raise UserError(_("Numéro requis pour le SIP trunk."))
            phone_number = provision.normalize_e164(phone_number)
            phone_source = "sip_trunk"
            trunk_id = payload.get("trunk_id")
            if trunk_id:
                trunk = self.env["doorway.sip.trunk"].browse(trunk_id).exists()
            if not trunk and payload.get("trunk_name"):
                trunk = self.env["doorway.sip.trunk"].create(
                    {
                        "name": payload["trunk_name"],
                        "provider": payload.get("trunk_provider") or "custom",
                        "twilio_trunk_sid": (
                            payload.get("twilio_sip_trunk_sid") or ""
                        ).strip(),
                        "termination_uri": (
                            payload.get("termination_uri") or ""
                        ).strip(),
                    }
                )
            if trunk:
                sip_trunk_name = trunk.name
                twilio_sip_trunk_sid = trunk.twilio_trunk_sid or ""
        else:
            phone_number = payload.get("phone_number")
            if not phone_number:
                raise UserError(_("Numéro de téléphone requis."))
            phone_number = provision.normalize_e164(phone_number)
            phone_source = "manual"
            sip_trunk_name = (payload.get("sip_trunk_name") or "").strip()
            twilio_sip_trunk_sid = (payload.get("twilio_sip_trunk_sid") or "").strip()
            trunk_id = payload.get("trunk_id")
            if trunk_id:
                trunk = self.env["doorway.sip.trunk"].browse(trunk_id).exists()

        existing = Phone.search(
            [
                ("agent_id", "=", self.id),
                ("phone_number", "=", phone_number),
            ],
            limit=1,
        )
        vals = {
            "name": payload.get("line_name") or _("Ligne principale"),
            "phone_number": phone_number,
            "phone_source": phone_source,
            "country_code": (payload.get("country_code") or "CA").upper(),
            "twilio_incoming_sid": twilio_sid,
            "sip_trunk_name": sip_trunk_name or (trunk.name if trunk else ""),
            "twilio_sip_trunk_sid": twilio_sip_trunk_sid
            or (trunk.twilio_trunk_sid if trunk else ""),
            "trunk_id": trunk.id if trunk else False,
            "usage": payload.get("usage") or "outbound",
            "active": True,
        }
        if existing:
            existing.write(vals)
            line = existing
        else:
            vals["agent_id"] = self.id
            line = Phone.create(vals)
        self._set_primary_phone_line(line)
        ph_id = self._link_phone_to_elevenlabs()
        result = self._wizard_telephony_payload()
        result["elevenlabs_phone_number_id"] = ph_id or result.get(
            "elevenlabs_phone_number_id", ""
        )
        return result

    def wizard_remove_phone(self):
        """Retire le numéro principal de l'agent (sans libérer Twilio)."""
        self.ensure_one()
        line = self.default_phone_number_id
        if line:
            line.write({"is_primary": False, "active": False})
        self.write({"default_phone_number_id": False})
        return self._wizard_telephony_payload()

    def action_open_edit_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "agent_wizard_action",
            "name": _("Modifier l'agent"),
            "context": {
                "default_agent_id": self.id,
                "open_wizard_step": self.wizard_step or "identity",
            },
        }

    def action_open_telephony_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "agent_wizard_action",
            "name": _("Téléphonie agent"),
            "context": {
                "default_agent_id": self.id,
                "open_wizard_step": "telephony",
            },
        }

    def action_archive_agent(self):
        """Désactive l'agent (réversible)."""
        self.ensure_one()
        self.write({"status": "inactive"})
        return True

    def action_delete_agent(self, release_twilio=False):
        """Supprime l'agent Odoo ; option pour libérer les numéros Twilio achetés."""
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.twilio_provision_service import (
            TwilioProvisionService,
        )

        if release_twilio:
            provision = TwilioProvisionService(self.env)
            for line in self.phone_number_ids.filtered(
                lambda p: p.phone_source == "twilio_purchased" and p.twilio_incoming_sid
            ):
                provision.release_number(line.twilio_incoming_sid)
        self.unlink()
        return {
            "type": "ir.actions.client",
            "tag": "agents_dashboard_action",
            "name": _("Agents IA"),
        }

    def wizard_deploy(self):
        """Provisionne l'agent ElevenLabs et passe en actif."""
        self.ensure_one()
        if not self.name:
            raise UserError(_("Nom de l'agent requis."))
        if not (self.voice_id or self.voice_clone_id):
            raise UserError(_("Sélectionnez une voix ElevenLabs."))
        if not self.system_prompt:
            raise UserError(_("Le prompt système est requis."))

        from odoo.addons.doorway_agents_dashboard.services.agent_provision import (
            AgentProvisionService,
        )

        external_id = AgentProvisionService(self.env).deploy_from_wizard(self)
        self.write(
            {
                "external_agent_id": external_id,
                "status": "active",
                "wizard_step": "summary",
                "last_sync": fields.Datetime.now(),
            }
        )
        self._link_phone_to_elevenlabs()
        return {"agent_id": self.id, "external_agent_id": external_id, "status": "active"}

    def wizard_start_test_call(self, phone_number):
        """Lance un appel test Twilio via ElevenLabs."""
        self.ensure_one()
        if not phone_number:
            raise UserError(_("Numéro de téléphone requis."))
        ext_id = (self.external_agent_id or "").strip()
        if not ext_id or ext_id.startswith("draft-"):
            if not (self.voice_id or self.voice_clone_id):
                raise UserError(
                    _("Sélectionnez une voix ElevenLabs à l'étape « Voix », puis réessayez.")
                )
            if not (self.system_prompt or "").strip():
                raise UserError(_("Renseignez le prompt système avant l'appel test."))
            self.wizard_deploy()
            ext_id = self.external_agent_id

        wizard = self.env["doorway.test.call.wizard"].create(
            {
                "agent_id": self.id,
                "phone_number": phone_number,
                "call_mode": "phone",
            }
        )
        return wizard.action_start_call()

    def wizard_start_web_test(self):
        """Lance un test web (micro navigateur) depuis le wizard (prompt ou récap)."""
        self.ensure_one()
        if self.provider not in ("n8n", "retell", "elevenlabs"):
            raise UserError(_("Fournisseur non supporté pour le test web."))
        ext_id = (self.external_agent_id or "").strip()
        if not ext_id or ext_id.startswith("draft-"):
            if not (self.voice_id or self.voice_clone_id):
                raise UserError(
                    _("Sélectionnez une voix ElevenLabs à l'étape « Voix », puis réessayez.")
                )
            if not (self.system_prompt or "").strip():
                raise UserError(_("Renseignez le prompt système avant le test web."))
            self.wizard_deploy()
        return self.action_open_web_test()
