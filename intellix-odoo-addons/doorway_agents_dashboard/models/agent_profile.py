# -*- coding: utf-8 -*-
import logging
import re
import base64
import requests
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AgentProfile(models.Model):
    _name = "doorway.agent.profile"
    _description = "Agent IA Profile (ElevenLabs / n8n)"
    _order = "pipeline, agent_type, name"

    name = fields.Char(string="Nom agent", required=True, index=True)
    provider = fields.Selection(
        [
            ("elevenlabs", "ElevenLabs"),
            ("n8n", "Agent IA (n8n + ElevenLabs + Twilio)"),
            ("retell", "Agent IA (legacy)"),
        ],
        string="Provider",
        required=True,
        index=True,
    )
    external_agent_id = fields.Char(
        string="ID agent (provider)",
        required=True,
        index=True,
    )
    pipeline = fields.Selection(
        [
            ("renovation", "Rénovation"),
            ("immobilier", "Immobilier"),
            ("marketing", "Marketing"),
            ("driven", "Driven (B2B)"),
            ("assurance", "Assurance"),
            ("doorway", "Doorway Clients"),
        ],
        string="Pipeline CRM",
        required=True,
        default="doorway",
    )
    agent_type = fields.Selection(
        [
            ("inbound", "Inbound"),
            ("outbound", "Outbound"),
            ("followup", "Suivi / Followup"),
        ],
        string="Type",
        required=True,
        default="inbound",
    )
    language = fields.Selection(
        [
            ("fr", "Français"),
            ("en", "Anglais"),
            ("es", "Español"),
            ("bilingual", "Bilingue / Multilingue"),
        ],
        string="Langue",
        default="fr",
    )
    timezone = fields.Char(string="Fuseau horaire", default="America/Toronto")
    voice_name = fields.Char(string="Voix")
    voice_gender = fields.Selection(
        [
            ("any", "Toutes"),
            ("female", "Femme"),
            ("male", "Homme"),
        ],
        string="Genre de voix",
        default="female",
    )
    voice_clone_id = fields.Char(string="Voice Clone ID")
    export_calls_google_sheet = fields.Boolean(
        string="Exporter appels vers Google Sheet",
        help="Enregistre chaque appel (transcription, coordonnées, enregistrement) "
        "directement dans Google Sheets, sans pipeline CRM.",
        default=False,
    )
    google_sheets_spreadsheet_id = fields.Char(
        string="Google Sheet ID (agent)",
        help="Optionnel — surcharge l'ID global. Ex. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    )
    google_sheets_webhook_url = fields.Char(
        string="Webhook Google Sheet (agent)",
        help="Optionnel — URL Apps Script pour cet agent uniquement.",
    )
    voice_sample_file = fields.Binary(
        string="Échantillon voix (audio)",
        attachment=True,
    )
    voice_sample_filename = fields.Char(string="Nom fichier voix")
    latency_target_ms = fields.Integer(string="Latence cible (ms)", default=1200)
    system_prompt = fields.Text(
        string="Prompt principal",
        help="Prompt de base utilisé par l'agent pour guider ses réponses.",
    )
    allow_send_email = fields.Boolean(string="Action: Envoyer e-mail", default=False)
    allow_send_sms = fields.Boolean(string="Action: Envoyer SMS", default=False)
    allow_availability_check = fields.Boolean(
        string="Action: Vérifier disponibilité horaire",
        default=False,
    )
    allow_human_transfer = fields.Boolean(
        string="Action: Transfert vers humain",
        default=False,
    )
    transfer_user_id = fields.Many2one("res.users", string="Utilisateur transfert")
    transfer_phone = fields.Char(string="Numéro transfert humain")
    calendar_user_id = fields.Many2one(
        "res.users",
        string="Compte calendrier",
        help="Utilisateur Odoo dont le calendrier représente la disponibilité de cet agent.",
        copy=False,
    )
    calendar_partner_id = fields.Many2one(
        "res.partner",
        string="Contact calendrier",
        related="calendar_user_id.partner_id",
        store=True,
        readonly=True,
    )
    calendar_share_public = fields.Boolean(
        string="Calendrier public (équipe)",
        default=True,
        help="Rend le calendrier visible aux collègues dans la vue Participants.",
    )
    status = fields.Selection(
        [
            ("active", "Actif"),
            ("inactive", "Inactif"),
            ("error", "Erreur"),
        ],
        string="Statut",
        default="active",
    )
    last_test_date = fields.Datetime(string="Dernier test")
    last_test_score = fields.Float(string="Score dernier test /100")
    avg_call_score = fields.Float(
        string="Score moyen /100",
        compute="_compute_avg_score",
        store=True,
    )
    total_test_calls = fields.Integer(string="Nb tests total", default=0)
    description = fields.Text(string="Notes internes")
    last_sync = fields.Datetime(string="Dernière sync API")
    test_call_ids = fields.One2many(
        "doorway.agent.test.call",
        "agent_id",
        string="Appels test",
    )
    volet_ids = fields.One2many(
        "doorway.agent.volet",
        "agent_id",
        string="Volets",
    )
    default_volet = fields.Selection(
        [
            ("reception", "Réception"),
            ("qualification", "Lead qualification"),
            ("cold_call", "Appel à froid"),
        ],
        string="Volet par défaut",
        default="reception",
        help="Volet utilisé si aucun n'est précisé à l'appel.",
    )
    immo_agent_role = fields.Selection(
        [
            ("j0_qualification", "Immo · J+0 Qualification"),
            ("j1_relance", "Immo · J+1 Relance"),
            ("j3_relance", "Immo · J+3 Relance"),
            ("j7_relance", "Immo · J+7 Relance"),
            ("j14_relance", "Immo · J+14 Re-engagement"),
        ],
        string="Rôle séquence immo",
        index=True,
        help="Identifiant stable pour Meta/n8n/CRM — ne pas utiliser le nom affiché.",
    )
    energie_agent_role = fields.Selection(
        [
            ("j0_qualification", "Énergie · J+0 Qualification"),
            ("j1_relance", "Énergie · J+1 Relance"),
            ("j3_relance", "Énergie · J+3 Relance"),
            ("j7_relance", "Énergie · J+7 Fermeture"),
        ],
        string="Rôle séquence Énergie Pro",
        index=True,
    )
    haidly_agent_role = fields.Selection(
        [
            ("j0_qualification", "Haidly · J+0 Qualification"),
            ("j1_relance", "Haidly · J+1 Relance"),
            ("j3_relance", "Haidly · J+3 Relance"),
            ("j7_relance", "Haidly · J+7 Fermeture"),
            ("j14_relance", "Haidly · J+14 Re-engagement"),
        ],
        string="Rôle séquence Haidly (SoumissionEntrepreneurs)",
        index=True,
    )
    phone_number_ids = fields.One2many(
        "doorway.agent.phone.number",
        "agent_id",
        string="Numéros assignés",
    )
    default_phone_number_id = fields.Many2one(
        "doorway.agent.phone.number",
        string="Numéro principal",
        domain="[('agent_id', '=', id), ('active', '=', True)]",
    )
    library_item_ids = fields.One2many(
        "doorway.agent.library.item",
        "agent_id",
        string="Bibliothèque agent",
    )

    _sql_constraints = [
        (
            "agent_profile_provider_external_uniq",
            "unique(provider, external_agent_id)",
            "Cet agent externe existe déjà pour ce fournisseur.",
        ),
    ]

    @api.depends("test_call_ids.score_global", "test_call_ids.state")
    def _compute_avg_score(self):
        for rec in self:
            calls = rec.test_call_ids.filtered(lambda c: c.state == "done")
            rec.avg_call_score = (
                sum(calls.mapped("score_global")) / len(calls) if calls else 0.0
            )

    def _ensure_calendar_user(self):
        """Crée ou met à jour le compte calendrier technique pour l'agent IA."""
        Users = self.env["res.users"].with_context(no_reset_password=True).sudo()
        group_user = self.env.ref("base.group_user")
        for agent in self:
            if agent.calendar_user_id:
                user = agent.calendar_user_id
            else:
                login = f"agent.cal.{agent.id}@doorway.ia"
                user = Users.search([("login", "=", login)], limit=1)
                if not user:
                    user = Users.create(
                        {
                            "name": f"IA — {agent.name}",
                            "login": login,
                            "email": login,
                            "group_ids": [(6, 0, [group_user.id])],
                            "doorway_is_ai_agent_user": True,
                            "doorway_agent_profile_id": agent.id,
                            "doorway_calendar_visible": agent.calendar_share_public,
                            "active": True,
                        }
                    )
                agent.calendar_user_id = user.id
            user.with_context(no_reset_password=True).write(
                {
                    "name": f"IA — {agent.name}",
                    "doorway_is_ai_agent_user": True,
                    "doorway_agent_profile_id": agent.id,
                    "doorway_calendar_visible": agent.calendar_share_public,
                    "active": True,
                }
            )
            if agent.calendar_share_public:
                user._doorway_ensure_public_calendar()

    def action_open_agent_calendar(self):
        self.ensure_one()
        if not self.calendar_user_id:
            self._ensure_calendar_user()
        action = self.env["ir.actions.actions"]._for_xml_id("calendar.action_calendar_event")
        action["context"] = dict(
            self.env.context,
            default_partner_ids=[self.calendar_partner_id.id],
        )
        return action

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered(lambda r: r.allow_availability_check)._ensure_calendar_user()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger = {"allow_availability_check", "calendar_share_public", "name", "status"}
        if trigger & set(vals.keys()):
            self.filtered(
                lambda r: r.allow_availability_check or r.calendar_user_id
            )._ensure_calendar_user()
        if vals.get("calendar_share_public"):
            self.env["res.users"].doorway_sync_calendar_filters()
        return res

    @api.model
    def _infer_pipeline(self, name):
        n = (name or "").lower()
        if re.search(r"driven|b2b", n):
            return "driven"
        if re.search(r"réno|reno|logis|isolation|énergie|energie", n):
            return "renovation"
        if re.search(r"immobilier|maison|recherch", n):
            return "immobilier"
        if re.search(r"market|digital", n):
            return "marketing"
        if re.search(r"dental|health|assurance|screening", n):
            return "assurance"
        return "doorway"

    @api.model
    def _infer_agent_type(self, name):
        n = (name or "").lower()
        if re.search(r"sortant|outbound", n):
            return "outbound"
        if re.search(r"suivi|follow", n):
            return "followup"
        if re.search(r"entrant|inbound", n):
            return "inbound"
        return "inbound"

    @api.model
    def _infer_language(self, name, api_lang=""):
        n = (name or "").lower()
        lang = (api_lang or "").lower()
        if "bilingual" in lang or "bilingue" in n:
            return "bilingual"
        if lang.startswith("es") or re.search(r"\bes\b|español|spanish|espagnol", n):
            return "es"
        if lang.startswith("en") or re.search(r"\ben\b|english| anglais", n):
            return "en"
        return "fr"

    def _resolve_volet(self, volet_code=None):
        """Retourne le code volet actif (reception / qualification / cold_call)."""
        self.ensure_one()
        code = (volet_code or self.default_volet or "reception").strip()
        if code not in ("reception", "qualification", "cold_call"):
            code = self.default_volet or "reception"
        volet = self.volet_ids.filtered(lambda v: v.code == code and v.active)[:1]
        if not volet and self.volet_ids:
            volet = self.volet_ids.filtered("active")[:1]
        return code if volet or not self.volet_ids else code

    def action_sync_from_api(self):
        """Sync manuelle depuis provider API."""
        for rec in self:
            if rec.provider == "elevenlabs":
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                ElevenLabsClient(rec.env).sync_agent(rec)
            elif rec.provider in ("n8n", "retell"):
                from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                    N8NClient,
                )

                N8NClient(rec.env).sync_agent(rec)

    @api.model
    def cron_sync_agents(self):
        """Synchronise tous les agents depuis ElevenLabs et n8n."""
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )
        from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
            N8NClient,
        )

        # Migration legacy Retell -> n8n pour garder les profils existants.
        self.sudo().search([("provider", "=", "retell")]).write({"provider": "n8n"})

        results = {"elevenlabs": 0, "n8n": 0, "errors": []}
        try:
            results["elevenlabs"] = ElevenLabsClient(self.env).sync_profiles()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Sync ElevenLabs agents")
            results["errors"].append("ElevenLabs: %s" % exc)
        try:
            results["n8n"] = N8NClient(self.env).sync_profiles()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Sync n8n agents")
            results["errors"].append("n8n: %s" % exc)
        _logger.info("doorway_agents_dashboard sync: %s", results)
        return results

    def action_sync_now(self):
        self.env["doorway.agent.profile"].cron_sync_agents()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Synchronisation"),
                "message": _("Agents ElevenLabs / n8n mis à jour."),
                "type": "success",
            },
        }

    def action_open_test_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tester — %s") % self.name,
            "res_model": "doorway.test.call.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_agent_id": self.id},
        }

    def action_open_web_test(self):
        """Test agent en appel web — stack n8n (prod) ou ElevenLabs legacy."""
        self.ensure_one()
        if self.provider not in ("n8n", "retell", "elevenlabs"):
            raise UserError(_("Fournisseur non supporté pour le test web."))
        ext_id = (self.external_agent_id or "").strip()
        if not ext_id or ext_id.startswith("draft-"):
            raise UserError(
                _(
                    "Agent non déployé sur ElevenLabs. "
                    "Terminez le wizard ou lancez le setup EL avant le test web."
                )
            )
        try:
            test_call = self.env["doorway.agent.test.call"].create(
                {
                    "agent_id": self.id,
                    "call_mode": "browser_mic",
                    "call_volet": self.default_volet,
                    "state": "pending",
                    "tested_by": self.env.uid,
                }
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("action_open_web_test agent %s", self.id)
            raise UserError(
                _("Impossible de créer l'appel test web : %s") % (exc,)
            ) from exc
        return {
            "type": "ir.actions.client",
            "tag": "agent_web_call_action",
            "name": _("Test web — %s") % self.name,
            "params": {"test_call_id": test_call.id},
        }

    def action_setup_sophie_elevenlabs(self):
        """Crée la voix (Rue_Ibnou_Jahir_3.m4a) + agent ConvAI ElevenLabs pour Maison Recherchée."""
        self.ensure_one()
        if self.immo_agent_role and self.immo_agent_role != "j0_qualification":
            raise UserError(
                _("Le setup Sophie s'applique à l'agent J+0 qualification uniquement.")
            )
        self.invalidate_recordset(["voice_sample_file", "voice_sample_filename"])

        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_setup import (
            ElevenLabsMaisonImmoSetup,
        )

        setup = ElevenLabsMaisonImmoSetup(self.env)
        update = bool(
            self.external_agent_id
            and self.external_agent_id not in ("ELEVENLABS_AGENT_ID_IMMO", "maison_recherchee")
        )
        result = setup.run_full_setup(self, update_existing=update)
        msg = _(
            "Voix: %(voice)s\nAgent: %(agent)s\nTrunk: %(trunk)s\nTransfert: %(transfer)s"
        ) % {
            "voice": result["voice_id"],
            "agent": result["agent_id"],
            "trunk": result["sip_trunk_sid"],
            "transfer": result["transfer_number"],
        }
        if result.get("test_audio_path"):
            msg += _("\nTest audio: %s") % result["test_audio_path"]
        relance = result.get("relance_agents") or {}
        if relance:
            msg += _("\n\nRelances:\n") + "\n".join(
                "%s → %s" % (k, v) for k, v in sorted(relance.items())
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Setup ElevenLabs terminé"),
                "message": msg,
                "type": "success",
                "sticky": True,
            },
        }

    def action_setup_energie_elevenlabs(self):
        """Crée voix + agent ConvAI ElevenLabs pour Énergie Pro (Alex)."""
        self.ensure_one()
        if self.energie_agent_role and self.energie_agent_role != "j0_qualification":
            raise UserError(
                _("Le setup Alex s'applique à l'agent J+0 Énergie Pro uniquement.")
            )
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_energie_setup import (
            ElevenLabsEnergieProSetup,
        )

        setup = ElevenLabsEnergieProSetup(self.env)
        update = bool(
            self.external_agent_id
            and self.external_agent_id
            not in ("ELEVENLABS_AGENT_ID_ENERGIE", "energie_pro")
        )
        result = setup.run_full_setup(self, update_existing=update)
        msg = _(
            "Voix: %(voice)s\nAgent: %(agent)s\nFrom: %(from)s\nTransfert: %(transfer)s"
        ) % {
            "voice": result["voice_id"],
            "agent": result["agent_id"],
            "from": result["from_number"],
            "transfer": result["transfer_number"],
        }
        relance = result.get("relance_agents") or {}
        if relance:
            msg += _("\n\nRelances:\n") + "\n".join(
                "%s → %s" % (k, v) for k, v in sorted(relance.items())
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Setup ElevenLabs Énergie Pro"),
                "message": msg,
                "type": "success",
                "sticky": True,
            },
        }

    def action_setup_energie_relance_elevenlabs(self):
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_energie_setup import (
            ElevenLabsEnergieProSetup,
        )

        setup = ElevenLabsEnergieProSetup(self.env)
        relance = setup.run_relance_setup(self, update_existing=True)
        msg = "\n".join("%s → %s" % (k, v) for k, v in sorted(relance.items()))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Relances Énergie Pro"),
                "message": msg or _("Aucun agent créé."),
                "type": "success",
                "sticky": True,
            },
        }

    def action_sync_voicemail_detection_elevenlabs(self):
        """Active détection répondeur + raccrochage sur tous les agents ElevenLabs."""
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        result = ElevenLabsClient(self.env).sync_voicemail_detection_all_outbound()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Détection répondeur ElevenLabs"),
                "message": _("%(ok)s / %(total)s agents mis à jour.")
                % result,
                "type": "success",
                "sticky": True,
            },
        }

    def action_setup_haidly_elevenlabs(self):
        """Crée voix + agent ConvAI ElevenLabs pour Haidly (SoumissionEntrepreneurs)."""
        self.ensure_one()
        if self.haidly_agent_role and self.haidly_agent_role != "j0_qualification":
            raise UserError(
                _("Le setup Haidly s'applique à l'agent J+0 uniquement.")
            )
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_haidly_setup import (
            ElevenLabsHaidlySetup,
        )

        setup = ElevenLabsHaidlySetup(self.env)
        update = bool(
            self.external_agent_id
            and self.external_agent_id
            not in ("ELEVENLABS_AGENT_ID_HAIDLY", "haidly")
        )
        result = setup.run_full_setup(self, update_existing=update)
        msg = _(
            "Voix: %(voice)s\nAgent: %(agent)s\nFrom: %(from)s\nTransfert: %(transfer)s"
        ) % {
            "voice": result["voice_id"],
            "agent": result["agent_id"],
            "from": result["from_number"],
            "transfer": result["transfer_number"],
        }
        relance = result.get("relance_agents") or {}
        if relance:
            msg += _("\n\nRelances:\n") + "\n".join(
                "%s → %s" % (k, v) for k, v in sorted(relance.items())
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Setup ElevenLabs Haidly"),
                "message": msg,
                "type": "success",
                "sticky": True,
            },
        }

    def action_setup_haidly_relance_elevenlabs(self):
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_haidly_setup import (
            ElevenLabsHaidlySetup,
        )

        setup = ElevenLabsHaidlySetup(self.env)
        relance = setup.run_relance_setup(self, update_existing=True)
        msg = "\n".join("%s → %s" % (k, v) for k, v in sorted(relance.items()))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Relances Haidly"),
                "message": msg or _("Aucun agent créé."),
                "type": "success",
                "sticky": True,
            },
        }

    def action_setup_relance_elevenlabs(self):
        """Crée / met à jour les 4 agents ConvAI de relance (J+1, J+3, J+7, J+14)."""
        self.ensure_one()
        if self.haidly_agent_role == "j0_qualification":
            return self.action_setup_haidly_relance_elevenlabs()
        if self.energie_agent_role == "j0_qualification":
            return self.action_setup_energie_relance_elevenlabs()
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_setup import (
            ElevenLabsMaisonImmoSetup,
        )

        setup = ElevenLabsMaisonImmoSetup(self.env)
        relance = setup.run_relance_setup(self, update_existing=True)
        msg = "\n".join("%s → %s" % (k, v) for k, v in sorted(relance.items()))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Agents relance ElevenLabs"),
                "message": msg or _("Aucun agent créé."),
                "type": "success",
                "sticky": True,
            },
        }

    def action_create_voice_clone(self):
        self.ensure_one()
        if self.provider != "elevenlabs":
            raise UserError(
                _("Le clonage voix est disponible uniquement pour les agents ElevenLabs.")
            )
        if not self.voice_sample_file:
            raise UserError(_("Veuillez joindre un fichier audio avant de créer la voix clone."))
        if not self.voice_name:
            raise UserError(_("Veuillez renseigner le nom de voix avant création."))

        audio_content = base64.b64decode(self.voice_sample_file)
        if len(audio_content) < 1024:
            raise UserError(_("Le fichier audio semble invalide ou trop petit."))

        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        try:
            result = ElevenLabsClient(self.env).create_voice_clone(
                self.voice_name,
                audio_content,
                self.voice_sample_filename or "voice_sample.wav",
            )
        except Exception as exc:  # noqa: BLE001
            raise UserError(_("Échec création voix clone ElevenLabs: %s") % exc) from exc

        self.write(
            {
                "voice_clone_id": result.get("voice_id") or "",
                "last_sync": fields.Datetime.now(),
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Voice clone créée"),
                "message": _("Voice ID: %s") % (self.voice_clone_id or "-"),
                "type": "success",
            },
        }

    def _update_test_stats(self, score):
        """Met à jour les compteurs après un appel test terminé."""
        self.ensure_one()
        self.write(
            {
                "last_test_date": fields.Datetime.now(),
                "last_test_score": score,
                "total_test_calls": self.total_test_calls + 1,
            }
        )

    def _is_energie_agent(self):
        """Agent énergie / thermopompe / isolation (script partagé Énergie Pro)."""
        self.ensure_one()
        name = (self.name or "").lower()
        return bool(
            self.energie_agent_role
            or any(
                hint in name
                for hint in (
                    "thermo",
                    "énergie",
                    "energie",
                    "isolation",
                    "portes",
                    "fenêtres",
                    "fenetres",
                    "ici therm",
                )
            )
        )

    def _linked_script_profile(self):
        """Profil Odoo source du script si cet agent n'a pas de prompt."""
        self.ensure_one()
        if (self.system_prompt or "").strip():
            return self
        if self._is_energie_agent():
            linked = self.env.ref(
                "doorway_agents_dashboard.agent_energie_pro",
                raise_if_not_found=False,
            )
            if linked and (linked.system_prompt or "").strip():
                return linked
        if self.immo_agent_role or "immo" in (self.name or "").lower():
            linked = self.search(
                [
                    ("immo_agent_role", "=", "j0_qualification"),
                    ("system_prompt", "!=", False),
                ],
                limit=1,
            )
            if linked:
                return linked
        return self

    def get_effective_prompt_info(self):
        """Prompt affiché à l'édition (propre, lié ou ElevenLabs)."""
        self.ensure_one()
        own = (self.system_prompt or "").strip()
        if own:
            return {
                "prompt": own,
                "source": "own",
                "linked_name": "",
                "linked_id": False,
            }
        linked = self._linked_script_profile()
        if linked != self:
            body = (linked.system_prompt or "").strip()
            if body:
                return {
                    "prompt": body,
                    "source": "linked",
                    "linked_name": linked.name,
                    "linked_id": linked.id,
                }
        if (
            self.provider == "elevenlabs"
            and self.external_agent_id
            and not str(self.external_agent_id).startswith("draft-")
        ):
            try:
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                bundle = ElevenLabsClient(self.env).fetch_agent_prompt_bundle(
                    self.external_agent_id
                )
                el_prompt = (bundle.get("prompt") or "").strip()
                if el_prompt:
                    return {
                        "prompt": el_prompt,
                        "source": "elevenlabs",
                        "linked_name": self.external_agent_id,
                        "linked_id": False,
                    }
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Prompt ElevenLabs indisponible pour %s: %s",
                    self.name,
                    exc,
                )
        return {
            "prompt": "",
            "source": "empty",
            "linked_name": "",
            "linked_id": False,
        }

    def action_open_prompt_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "agent_wizard_action",
            "name": _("Modifier le prompt"),
            "context": {
                "default_agent_id": self.id,
                "open_wizard_step": "prompt",
            },
        }

    def _default_energie_lead_site(self):
        """Site source pour ouverture test (thermopompe / isolation / portes)."""
        self.ensure_one()
        name = (self.name or "").lower()
        if "isolation" in name:
            return "isolationqc"
        if "porte" in name or "fenêtre" in name or "fenetre" in name:
            return "portesetfenetresqc"
        return "icithermopompe"

    def _effective_system_prompt(self):
        """Prompt réellement utilisé (propre, lié ou ElevenLabs)."""
        self.ensure_one()
        return (self.get_effective_prompt_info().get("prompt") or "").strip()

    IMPROVEMENTS_MARKER = "## Améliorations suggérées"

    @api.model
    def _strip_questions_block(self, prompt):
        return re.sub(
            r"QUESTIONS\s*\(ordre[^)]*\)\s*:.*?(?=\n(?:TRANSFERT|RÈGLES|CLÔTURE|SI NON|AVANT TRANSFERT)\b|\Z)",
            "",
            prompt or "",
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()

    @api.model
    def _immo_j0_canonical_prompt(self):
        """Script J+0 Meta — texte de référence (copié sur la fiche Odoo)."""
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_maison_immo import (
            SOPHIE_J0_QUALIFICATION_PROMPT,
        )

        return SOPHIE_J0_QUALIFICATION_PROMPT

    @api.model
    def _haidly_j0_canonical_prompt(self):
        """Script J+0 Haidly Meta — texte de référence (copié sur la fiche Odoo)."""
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_haidly import (
            HAIDLY_J0_QUALIFICATION_PROMPT,
        )

        return HAIDLY_J0_QUALIFICATION_PROMPT

    @api.model
    def sync_immo_j0_prompt_to_odoo(self):
        """Écrit le script J+0 sur la fiche agent Odoo (source de vérité éditable)."""
        canonical = self._immo_j0_canonical_prompt()
        updated = 0
        j0_agents = self.sudo().search(
            [
                ("immo_agent_role", "=", "j0_qualification"),
                ("status", "=", "active"),
            ]
        )
        for agent in j0_agents:
            current = (agent.system_prompt or "").strip()
            legacy = (
                not current
                or "MISSION:" not in current
                or "propriété au {{property_address}}" in current
                or "QUESTIONS (ordre):" in current
            )
            if legacy:
                agent.write({"system_prompt": canonical})
                updated += 1
                ext = (agent.external_agent_id or "").strip()
                if ext.startswith("agent_"):
                    twins = self.search(
                        [
                            ("external_agent_id", "=", ext),
                            ("id", "!=", agent.id),
                            ("status", "=", "active"),
                        ]
                    )
                    if twins:
                        twins.write({"system_prompt": canonical})
        _logger.info("sync_immo_j0_prompt_to_odoo: %s agents mis à jour", updated)
        return updated

    @api.model
    def sync_haidly_j0_prompt_to_odoo(self):
        """Écrit le script J+0 Haidly sur la fiche agent Odoo (source de vérité éditable)."""
        canonical = self._haidly_j0_canonical_prompt()
        updated = 0
        j0_agents = self.sudo().search(
            [
                ("haidly_agent_role", "=", "j0_qualification"),
                ("status", "=", "active"),
            ]
        )
        for agent in j0_agents:
            current = (agent.system_prompt or "").strip()
            legacy = (
                not current
                or "MISSION:" not in current
                or "BLOC 1" not in current
                or "Objectif unique en moins de 2 minutes" in current
                or len(current) < 2000
            )
            if legacy:
                agent.write({"system_prompt": canonical})
                updated += 1
                ext = (agent.external_agent_id or "").strip()
                if ext.startswith("agent_"):
                    twins = self.search(
                        [
                            ("external_agent_id", "=", ext),
                            ("id", "!=", agent.id),
                            ("status", "=", "active"),
                        ]
                    )
                    if twins:
                        twins.write({"system_prompt": canonical})
        _logger.info("sync_haidly_j0_prompt_to_odoo: %s agents mis à jour", updated)
        return updated

    @api.model
    def _is_immo_j0_script(self, base, improvements=""):
        blob = ((base or "") + "\n" + (improvements or "")).lower()
        return "maison recherchée" in blob or "évaluation marchande" in blob

    @api.model
    def _inject_questions_block(self, base, questions_block):
        base = (base or "").strip()
        if re.search(r"TRANSFERT\s+HUMAIN", base, re.IGNORECASE):
            return re.sub(
                r"\n(TRANSFERT\s+HUMAIN)",
                "\n\n%s\n\n\\1" % questions_block,
                base,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
        return (base + "\n\n" + questions_block).strip()

    @api.model
    def _compile_runtime_prompt(self, prompt):
        """Fusionne les améliorations Claude dans un script exécutable (plus d'annexe)."""
        prompt = (prompt or "").strip()
        marker = self.IMPROVEMENTS_MARKER
        if not prompt or marker not in prompt:
            return prompt
        base, improvements = prompt.split(marker, 1)
        base = self._strip_questions_block(base.strip())
        improvements = improvements.strip()
        if improvements.startswith("(Claude)"):
            improvements = improvements[len("(Claude)") :].strip()
        if self._is_immo_j0_script(base, improvements):
            return self._immo_j0_canonical_prompt()
        else:
            questions = (
                "QUESTIONS (ordre strict — appliquer les améliorations ci-dessous):\n"
                + improvements
            )
        return self._inject_questions_block(base, questions)

    def materialize_compiled_prompt(self):
        """Écrit le script compilé sur la fiche agent (supprime l'annexe améliorations)."""
        self.ensure_one()
        raw = (self.system_prompt or "").strip()
        if not raw:
            return False
        compiled = self._runtime_system_prompt()
        if compiled and compiled != raw:
            self.write({"system_prompt": compiled})
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
                    twins.write({"system_prompt": compiled})
            return True
        return False

    def _haidly_j0_default_opening(self):
        return (
            "Bonjour {{lead_name}}, je m'appelle Haidly et j'appelle de la part de "
            "SoumissionEntrepreneurs suite à votre demande soumise en ligne. "
            "Est-ce que je vous parle bien à {{lead_name}}?"
        )

    @api.model
    def _is_valid_agent_opening(self, opening):
        text = (opening or "").strip()
        if len(text) < 25:
            return False
        if "appel ainsi" in text.lower():
            return False
        lower = text.lower()
        return lower.startswith(
            ("bonjour", "buenos días", "buenos dias", "hola", "hello")
        )

    def _normalize_haidly_j0_prompt(self, prompt):
        """Script J+0 Haidly exécutable (sans tagline design / plans 3D)."""
        own = (self.system_prompt or "").strip()
        if own and "MISSION:" in own and "BLOC 1" in own:
            return own
        prompt = (prompt or "").strip()
        if not prompt:
            return self._haidly_j0_canonical_prompt()
        if "MISSION:" in prompt and "BLOC 1" in prompt:
            return prompt
        if (
            "QUESTIONS (ordre strict" in prompt
            and "OUVERTURE:" in prompt.upper()
            and "propriétaire" in prompt.lower()
        ):
            existing = self._extract_opening_from_system_prompt(prompt, "haidly")
            if self._is_valid_agent_opening(existing):
                return prompt
        opening = self._extract_opening_from_system_prompt(prompt, "haidly")
        if not self._is_valid_agent_opening(opening):
            opening = self._haidly_j0_default_opening()
        return (
            "Tu es Haidly, agent de qualification sortant pour SoumissionEntrepreneurs.com.\n"
            "Objectif unique en moins de 2 minutes: (1) confirmer propriétaire, "
            "(2) confirmer projet rénovation (cuisine, SDB, sous-sol, patio, agrandissement), "
            "(3) confirmer disponibilité pour un conseiller. Si les 3 critères sont OK → transfert immédiat.\n\n"
            "VARIABLES: {{lead_name}}, {{project_type}}, {{city}}, {{property_type}}, {{lead_id_odoo}}\n\n"
            'OUVERTURE: "%s"\n\n'
            "QUESTIONS (ordre strict — une question à la fois, ne jamais sauter d'étape):\n"
            "1. PROPRIÉTAIRE (obligatoire en premier): « Êtes-vous propriétaire du logement à rénover? » "
            "Si NON → terminer poliment.\n"
            "2. TYPE DE PROJET: « Quel type de projet avez-vous en tête? » "
            "— cuisine, salle de bain, sous-sol, patio ou agrandissement uniquement.\n"
            "3. DISPONIBILITÉ CONSEILLER: « Avez-vous quelques minutes maintenant pour parler avec "
            "un conseiller qui peut finaliser votre rendez-vous avec un entrepreneur? »\n\n"
            "RÈGLES: Direct, chaleureux, bref. Moins de 2 minutes. "
            "INTERDIT: plans 3D, design, subventions, présentation de services à cette étape.\n"
            "TRANSFERT si 3 critères OK: « Parfait, je vous transfère maintenant à un conseiller "
            "qui va s'occuper de tout pour vous. Un instant s'il vous plaît. »"
        ) % opening.replace('"', "'")

    def _normalize_immo_j0_prompt(self, prompt):
        """Migration legacy → script Odoo J+0 (ne remplace pas un prompt Odoo à jour)."""
        own = (self.system_prompt or "").strip()
        if own and "MISSION:" in own and "RÈGLE ADRESSE" in own:
            return own
        prompt = (prompt or "").strip()
        if prompt and "MISSION:" in prompt and "RÈGLE ADRESSE" in prompt:
            return prompt
        return self._immo_j0_canonical_prompt()

    def _runtime_system_prompt(self):
        """Prompt effectif — le champ system_prompt Odoo est la source de vérité."""
        self.ensure_one()
        own = (self.system_prompt or "").strip()
        if self.immo_agent_role == "j0_qualification" and own and "MISSION:" in own:
            return own
        if self.haidly_agent_role == "j0_qualification" and own and "MISSION:" in own:
            return own
        if self.haidly_agent_role == "j0_qualification" and not own:
            return self._haidly_j0_canonical_prompt()
        compiled = self._compile_runtime_prompt(self._effective_system_prompt())
        if self.immo_agent_role == "j0_qualification":
            compiled = self._normalize_immo_j0_prompt(compiled)
        elif self.haidly_agent_role == "j0_qualification":
            compiled = self._normalize_haidly_j0_prompt(compiled)
        return compiled

    @api.model
    def _extract_opening_from_system_prompt(self, prompt, site="icithermopompe"):
        """Extrait la phrase d'ouverture du script Odoo (énergie, immo, générique)."""
        prompt = (prompt or "").strip()
        if not prompt:
            return ""
        ouverture = re.search(
            r'(?im)^\s*ouverture\s*:\s*["\u201c]?(.+?)["\u201d]?\s*$',
            prompt,
        )
        if not ouverture:
            ouverture = re.search(
                r'(?i)ouverture\s*:\s*["\u201c]([^"\u201d]+)["\u201d]',
                prompt,
            )
        if not ouverture:
            ouverture = re.search(
                r'(?i)ouverture\s*:\s*(Bonjour[^\n]+)',
                prompt,
            )
        if not ouverture:
            ouverture = re.search(
                r"(?is)ouverture\s+obligatoire\s*:.*?(?:ainsi\s*:\s*)?['\u2018]"
                r"(Bonjour.+?\?)['\u2019]",
                prompt,
            )
        if ouverture:
            text = ouverture.group(1).strip().strip('"').strip("\u201c\u201d")
            return text.replace("[Prénom]", "{{lead_name}}").replace(
                "[prenom]", "{{lead_name}}"
            )
        lower = prompt.lower()
        site_markers = {
            "icithermopompe": ("icithermopompe", "thermopompe"),
            "isolationqc": ("isolationqc", "isolation"),
            "portesetfenetresqc": (
                "portesetfenetres",
                "portes et fenêtres",
                "portes et fenetres",
            ),
            "immo": ("maison recherchée", "sophie", "évaluation marchande"),
            "haidly": (
                "soumissionentrepreneurs",
                "haidly",
                "je m'appelle haidly",
            ),
        }
        markers = site_markers.get(site, (site,))
        idx = -1
        for marker in markers:
            pos = lower.find(marker)
            if pos >= 0:
                idx = pos
                break
        chunk = prompt[idx:] if idx >= 0 else prompt
        quoted = re.search(
            r'["\u201c](Bonjour[^"\u201d]+)["\u201d]',
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if quoted:
            return quoted.group(1).strip()
        inline = re.search(
            r"(Bonjour\s*\{\{lead_name\}\}[^\n\"]+)",
            chunk,
            re.IGNORECASE,
        )
        if inline:
            return inline.group(1).strip()
        return ""

    def get_web_test_first_message(self):
        """Premier message ConvAI — extrait du script effectif Odoo."""
        self.ensure_one()
        prompt = self._runtime_system_prompt() or self._effective_system_prompt()
        if prompt:
            site = self._default_energie_lead_site()
            if self.immo_agent_role or self.pipeline == "immobilier":
                site = "immo"
            elif self.haidly_agent_role:
                site = "haidly"
            opening = self._extract_opening_from_system_prompt(prompt, site)
            if self._is_valid_agent_opening(opening):
                return opening
        if self.immo_agent_role or self.pipeline == "immobilier":
            from odoo.addons.doorway_agents_dashboard.services.elevenlabs_maison_immo import (
                SOPHIE_FIRST_MESSAGE,
            )

            return SOPHIE_FIRST_MESSAGE
        if self.haidly_agent_role == "j0_qualification":
            return self._haidly_j0_default_opening()
        if self._is_energie_agent():
            site = self._default_energie_lead_site()
            defaults = {
                "icithermopompe": (
                    "Bonjour {{lead_name}}, c'est Alex d'Énergie Pro. "
                    "Vous avez fait une demande sur IciThermopompe.com. "
                    "Je vous appelle pour maximiser vos subventions. Deux-trois minutes?"
                ),
                "isolationqc": (
                    "Bonjour {{lead_name}}, c'est Alex d'Énergie Pro. "
                    "Vous avez demandé de l'info sur l'isolation via IsolationQC. "
                    "Je vous appelle pour optimiser vos subventions Rénoclimat. Deux minutes?"
                ),
                "portesetfenetresqc": (
                    "Bonjour {{lead_name}}, c'est Alex d'Énergie Pro. "
                    "Vous avez demandé de l'info portes et fenêtres. "
                    "Je vous appelle pour voir quelles subventions s'appliquent. Deux minutes?"
                ),
            }
            return defaults.get(site, "")
        return ""

    def _resolve_elevenlabs_voice_id(self):
        """Voice ID pour provisionnement (propre, lié ou Énergie Pro)."""
        self.ensure_one()
        vid = (self.voice_id or self.voice_clone_id or "").strip()
        if vid:
            return vid
        linked = self._linked_script_profile()
        if linked != self:
            vid = (linked.voice_id or linked.voice_clone_id or "").strip()
            if vid:
                return vid
        energie = self.env.ref(
            "doorway_agents_dashboard.agent_energie_pro",
            raise_if_not_found=False,
        )
        if energie:
            return (energie.voice_id or energie.voice_clone_id or "").strip()
        return ""

    def _elevenlabs_prompt_patch_payload(self):
        """Payload léger : prompt effectif + ouverture + overrides navigateur."""
        self.ensure_one()
        lang = self.language or "fr"
        el_lang = {"fr": "fr", "en": "en", "es": "es", "bilingual": "en"}.get(
            lang, "fr"
        )
        prompt_body = self._runtime_system_prompt()
        first_message = self.get_web_test_first_message()
        prompt_cfg = {
            "prompt": prompt_body,
            "max_tokens": 500,
            "temperature": 0.35,
        }
        if self.immo_agent_role == "j0_qualification" or self.haidly_agent_role == "j0_qualification":
            prompt_cfg["ignore_default_personality"] = True
        agent_cfg = {
            "prompt": prompt_cfg,
            "language": el_lang,
        }
        if first_message:
            agent_cfg["first_message"] = first_message
        return {
            "conversation_config": {"agent": agent_cfg},
            "platform_settings": {
                "overrides": {
                    "conversation_config_override": {
                        "agent": {
                            "first_message": True,
                            "language": True,
                            "prompt": {"prompt": True},
                        },
                    },
                },
            },
        }

    def sync_prompt_to_elevenlabs(self):
        """Pousse le prompt Odoo vers ElevenLabs (crée l'agent si l'ID est invalide)."""
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.agent_provision import (
            AgentProvisionService,
        )
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            BASE,
        )

        if not self._effective_system_prompt():
            return {"ok": False, "message": _("Prompt vide.")}
        svc = AgentProvisionService(self.env)
        if not svc.client.is_available():
            return {"ok": False, "message": _("Clé ElevenLabs absente.")}
        payload = self._elevenlabs_prompt_patch_payload()

        ext = (self.external_agent_id or "").strip()
        if ext and ext.startswith("agent_"):
            response = requests.patch(
                "%s/convai/agents/%s" % (BASE, ext),
                headers=svc.client.headers,
                json=payload,
                timeout=60,
            )
            if response.status_code < 400:
                svc.client.enable_web_test_overrides(ext)
                return {"ok": True, "agent_id": ext, "created": False}

        voice_id = self._resolve_elevenlabs_voice_id()
        if not voice_id:
            return {
                "ok": False,
                "message": _("Voice ID manquant pour créer l'agent ElevenLabs."),
            }
        if not (self.voice_id or self.voice_clone_id):
            self.write({"voice_id": voice_id, "voice_clone_id": voice_id})
        create_payload = svc._build_payload(self)
        create_payload["platform_settings"] = payload["platform_settings"]
        response = requests.post(
            "%s/convai/agents/create" % BASE,
            headers=svc.client.headers,
            json=create_payload,
            timeout=60,
        )
        if response.status_code >= 400:
            return {
                "ok": False,
                "message": svc.client.parse_api_error(response),
            }
        body = response.json()
        new_id = body.get("agent_id") or body.get("id") or ""
        if not new_id:
            return {"ok": False, "message": _("Réponse ElevenLabs sans agent_id.")}
        svc.client.sync_voicemail_detection_on_agent(new_id)
        svc.client.enable_web_test_overrides(new_id)
        self.write({"external_agent_id": new_id, "voice_id": voice_id, "voice_clone_id": voice_id})
        return {"ok": True, "agent_id": new_id, "created": True}

    @api.model
    def materialize_all_compiled_prompts(self):
        """Intègre les améliorations Claude dans le corps du script (tous agents actifs)."""
        count = 0
        for agent in self.sudo().search([("status", "=", "active")]):
            if agent.materialize_compiled_prompt():
                count += 1
        _logger.info("Materialize prompts: %s agents mis à jour", count)
        return count

    @api.model
    def sync_all_active_prompts_to_elevenlabs(self):
        """Pousse le prompt effectif de chaque agent actif vers ElevenLabs (1× par agent_id EL)."""
        self.materialize_all_compiled_prompts()
        synced = set()
        ok_count = 0
        errors = []
        agents = self.sudo().search(
            [("status", "=", "active")],
            order="provider desc, id asc",
        )
        for agent in agents:
            ext = (agent.external_agent_id or "").strip()
            if not ext.startswith("agent_") or ext in synced:
                continue
            if not agent._effective_system_prompt():
                continue
            synced.add(ext)
            try:
                res = agent.sync_prompt_to_elevenlabs()
                if res.get("ok"):
                    ok_count += 1
                else:
                    errors.append("%s: %s" % (agent.name, res.get("message")))
            except Exception as exc:  # noqa: BLE001
                errors.append("%s: %s" % (agent.name, exc))
                _logger.warning("Sync bulk prompt %s: %s", agent.id, exc)
        _logger.info(
            "Sync prompts ElevenLabs: %s agents, %s erreurs",
            ok_count,
            len(errors),
        )
        return {"ok": ok_count, "errors": errors, "synced_ids": list(synced)}

    def _dashboard_agent_score_pct(self, agent):
        return round(float(agent.avg_call_score or agent.last_test_score or 0))

    def _dashboard_sparkline(self, agent, days=7):
        rows = agent.get_calls_per_day(agent.id, days) if hasattr(agent, "get_calls_per_day") else []
        if not rows:
            return [0] * days
        return [
            (r.get("humains") or 0)
            + (r.get("repondeurs") or 0)
            + (r.get("leads") or 0)
            for r in rows
        ]

    def _dashboard_build_domain(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get("provider") and filters["provider"] != "all":
            domain.append(("provider", "=", filters["provider"]))
        if filters.get("pipeline") and filters["pipeline"] != "all":
            domain.append(("pipeline", "=", filters["pipeline"]))
        if filters.get("agent_type") and filters["agent_type"] != "all":
            domain.append(("agent_type", "=", filters["agent_type"]))
        status = filters.get("status") or "all"
        if status == "active":
            domain.append(("status", "=", "active"))
        elif status == "inactive":
            domain.append(("status", "in", ["inactive", "error"]))
        return domain

    def _dashboard_agent_payload(self, agent, phone_map=None):
        phone_map = phone_map or {}
        pid = agent.default_phone_number_id.id if agent.default_phone_number_id else False
        score = self._dashboard_agent_score_pct(agent)
        return {
            "id": agent.id,
            "name": agent.name,
            "provider": agent.provider,
            "pipeline": agent.pipeline,
            "agent_type": agent.agent_type,
            "status": agent.status,
            "total_test_calls": agent.total_test_calls,
            "avg_call_score": agent.avg_call_score,
            "last_test_score": agent.last_test_score,
            "score_pct": score,
            "language": agent.language,
            "voice_name": agent.voice_name,
            "latency_ms": agent.latency_target_ms or 0,
            "phone_display": phone_map.get(pid, "") if pid else "",
            "sparkline": self._dashboard_sparkline(agent, 7),
            "last_sync": fields.Datetime.to_string(agent.last_sync)
            if agent.last_sync
            else "",
        }

    @api.model
    def get_agents_ia_dashboard(self, filters=None):
        """Données agrégées pour le tableau de bord Agents IA (KPI + grilles)."""
        filters = filters or {}
        profiles = self.search(self._dashboard_build_domain(filters), order="status, name")
        since_24h = fields.Datetime.now() - timedelta(hours=24)
        TestCall = self.env["doorway.agent.test.call"]
        Session = self.env["doorway.call.session"]
        tests_24h = TestCall.search_count([("create_date", ">=", since_24h)])
        sessions_24h = Session.search_count([("date_start", ">=", since_24h)])
        calls_24h = tests_24h + sessions_24h

        active = profiles.filtered(lambda p: p.status == "active")
        scored = active.filtered(lambda p: self._dashboard_agent_score_pct(p) > 0)
        if scored:
            success_rate = round(
                sum(self._dashboard_agent_score_pct(p) for p in scored) / len(scored)
            )
        else:
            done = TestCall.search(
                [
                    ("create_date", ">=", since_24h),
                    ("state", "=", "done"),
                    ("score_global", ">", 0),
                ]
            )
            success_rate = (
                round(sum(done.mapped("score_global")) / len(done))
                if done
                else 0
            )

        latencies = [p.latency_target_ms or 0 for p in active if p.latency_target_ms]
        latency_ms = int(sum(latencies) / len(latencies)) if latencies else 1200

        phone_ids = profiles.mapped("default_phone_number_id").ids
        phone_map = {}
        if phone_ids:
            for ph in self.env["doorway.agent.phone.number"].browse(phone_ids):
                phone_map[ph.id] = ph.phone_number

        agents = [self._dashboard_agent_payload(p, phone_map) for p in profiles]
        optimal = []
        new_agents = []
        for agent, payload in zip(profiles, agents):
            if agent.status != "active":
                continue
            score = payload["score_pct"]
            tests = agent.total_test_calls or 0
            if score >= 65 and tests >= 2:
                optimal.append(
                    {
                        "id": payload["id"],
                        "name": payload["name"],
                        "score_pct": score,
                        "success_rate": score,
                        "calls_7d": sum(payload["sparkline"]),
                        "pipeline": payload["pipeline"],
                    }
                )
            else:
                new_agents.append(
                    {
                        "id": payload["id"],
                        "name": payload["name"],
                        "provider": payload["provider"],
                        "pipeline": payload["pipeline"],
                        "total_test_calls": tests,
                        "created_days": (
                            (fields.Datetime.now() - agent.create_date).days
                            if agent.create_date
                            else 0
                        ),
                    }
                )
        optimal.sort(key=lambda x: (-x["score_pct"], x["name"]))
        new_agents.sort(key=lambda x: (x["total_test_calls"], x["name"]))

        return {
            "global_kpis": {
                "success_rate": success_rate,
                "latency_ms": latency_ms,
                "calls_24h": calls_24h,
            },
            "agents": agents,
            "optimal_agents": optimal[:12],
            "new_agents": new_agents[:12],
            "counts": {
                "total": len(profiles),
                "active": len(active),
                "tests_total": sum(profiles.mapped("total_test_calls")),
            },
        }

    @api.model
    def get_dashboard_data(self):
        """Compatibilité — ancien endpoint."""
        data = self.get_agents_ia_dashboard({})
        return {
            "total_agents": data["counts"]["total"],
            "active_count": data["counts"]["active"],
            "tests_today": data["global_kpis"]["calls_24h"],
            "avg_score_today": data["global_kpis"]["success_rate"],
            "agents": data["agents"],
        }

    @api.model
    def _assign_martin_transfer_user(self):
        """Transfert humain ElevenLabs → Martin (+14389929200)."""
        martin = (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    ("login", "=", "martin@agencedoorway.com"),
                    ("active", "=", True),
                    ("share", "=", False),
                ],
                limit=1,
            )
        )
        if not martin:
            return
        for xmlid in (
            "doorway_agents_dashboard.agent_maison_recherchee",
            "doorway_agents_dashboard.agent_energie_pro",
            "doorway_agents_dashboard.agent_haidly",
        ):
            agent = self.env.ref(xmlid, raise_if_not_found=False)
            if not agent or not agent.allow_human_transfer:
                continue
            agent.write(
                {
                    "transfer_user_id": martin.id,
                    "transfer_phone": agent.transfer_phone or "+14389929200",
                }
            )

    @api.model
    def get_maison_immo_qualification_profile(self):
        """Profil J+0 Meta (xmlid agent_maison_recherchee ou rôle j0_qualification)."""
        unified = self.env.ref(
            "doorway_agents_dashboard.agent_maison_recherchee",
            raise_if_not_found=False,
        )
        if unified and unified.status == "active":
            return unified
        return self.sudo().search(
            [
                ("immo_agent_role", "=", "j0_qualification"),
                ("status", "=", "active"),
            ],
            limit=1,
        )

    @api.model
    def _post_init_maison_recherchee(self):
        """Finalise J+0, rôles relance, désactive doublons et leads test."""
        Profile = self.sudo()
        unified = self.env.ref(
            "doorway_agents_dashboard.agent_maison_recherchee",
            raise_if_not_found=False,
        )
        role_xmlids = (
            ("j0_qualification", "agent_maison_recherchee", "Maison Recherchée · J+0 Qualification"),
            ("j1_relance", "agent_maison_relance_j1", "Maison Recherchée · J+1 Relance"),
            ("j3_relance", "agent_maison_relance_j3", "Maison Recherchée · J+3 Relance"),
            ("j7_relance", "agent_maison_relance_j7", "Maison Recherchée · J+7 Relance"),
            ("j14_relance", "agent_maison_relance_j14", "Maison Recherchée · J+14 Re-engagement"),
        )
        canonical_ids = set()
        for role, xmlid, display_name in role_xmlids:
            rec = self.env.ref(
                "doorway_agents_dashboard.%s" % xmlid,
                raise_if_not_found=False,
            )
            if not rec:
                continue
            canonical_ids.add(rec.id)
            vals = {"immo_agent_role": role, "name": display_name}
            if role == "j0_qualification":
                vals.update(
                    {
                        "provider": "elevenlabs",
                        "pipeline": "immobilier",
                        "default_volet": "qualification",
                        "agent_type": "outbound",
                        "status": "active",
                    }
                )
            rec.write(vals)
        Profile.sync_immo_j0_prompt_to_odoo()

        if unified:
            phone = self.env.ref(
                "doorway_agents_dashboard.agent_maison_recherchee_phone",
                raise_if_not_found=False,
            )
            if phone:
                unified.write({"default_phone_number_id": phone.id})

        immo_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_agents_dashboard.elevenlabs_agent_id_immo")
            or ""
        ).strip()
        if immo_id and unified:
            dupes = Profile.search(
                [
                    ("external_agent_id", "=", immo_id),
                    ("id", "!=", unified.id),
                    ("status", "=", "active"),
                ]
            )
            if dupes:
                dupes.write({"status": "inactive"})

        legacy_names = (
            "Maison Recherchée",
            "Maison Recherchée Lead qualification",
            "maison_recherche",
            "Sortant - Maison Recherchee",
            "Sophie — Qualification Immo Doorway",
            "Sophie — Relance J+1 Maison Recherchée",
            "Sophie — Relance J+3 Angle Marché",
            "Sophie — Relance J+7 Dernière Chance",
            "Sophie — Re-engagement J+14 Immo",
        )
        legacy = Profile.search(
            [
                ("pipeline", "=", "immobilier"),
                ("name", "in", legacy_names),
                ("id", "not in", list(canonical_ids)),
            ]
        )
        if legacy:
            legacy.write({"status": "inactive"})

        Lead = self.env["crm.lead"].sudo()
        test_domain = [
            "|",
            ("name", "ilike", "Validation Meta"),
            ("name", "ilike", "Val2 Meta"),
        ]
        if "immo_meta_lead_id" in Lead._fields:
            test_domain = [
                "|",
                "|",
                ("immo_meta_lead_id", "in", ("test-validation-001", "val-002")),
                ("name", "ilike", "Validation Meta"),
                ("name", "ilike", "Val2 Meta"),
            ]
        test_leads = Lead.search(test_domain)
        if test_leads:
            test_leads.unlink()

        self._assign_martin_transfer_user()

    @api.model
    def get_energie_pro_qualification_profile(self):
        unified = self.env.ref(
            "doorway_agents_dashboard.agent_energie_pro",
            raise_if_not_found=False,
        )
        if unified and unified.status == "active":
            return unified
        return self.sudo().search(
            [
                ("energie_agent_role", "=", "j0_qualification"),
                ("status", "=", "active"),
            ],
            limit=1,
        )

    @api.model
    def _post_init_energie_pro(self):
        Profile = self.sudo()
        role_xmlids = (
            ("j0_qualification", "agent_energie_pro", "Énergie Pro · J+0 Qualification"),
            ("j1_relance", "agent_energie_relance_j1", "Énergie Pro · J+1 Relance"),
            ("j3_relance", "agent_energie_relance_j3", "Énergie Pro · J+3 Relance"),
            ("j7_relance", "agent_energie_relance_j7", "Énergie Pro · J+7 Fermeture"),
        )
        canonical_ids = set()
        unified = None
        for role, xmlid, display_name in role_xmlids:
            rec = self.env.ref(
                "doorway_agents_dashboard.%s" % xmlid,
                raise_if_not_found=False,
            )
            if not rec:
                continue
            canonical_ids.add(rec.id)
            if role == "j0_qualification":
                unified = rec
            vals = {"energie_agent_role": role, "name": display_name}
            if role == "j0_qualification":
                vals.update(
                    {
                        "provider": "elevenlabs",
                        "pipeline": "renovation",
                        "default_volet": "qualification",
                        "agent_type": "outbound",
                        "status": "active",
                        "transfer_phone": "+14389929200",
                    }
                )
            rec.write(vals)

        if unified:
            phone = self.env.ref(
                "doorway_agents_dashboard.agent_energie_pro_phone",
                raise_if_not_found=False,
            )
            if phone:
                unified.write({"default_phone_number_id": phone.id})

        energie_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_agents_dashboard.elevenlabs_agent_id_energie")
            or ""
        ).strip()
        if energie_id and unified:
            dupes = Profile.search(
                [
                    ("external_agent_id", "=", energie_id),
                    ("id", "!=", unified.id),
                    ("status", "=", "active"),
                ]
            )
            if dupes:
                dupes.write({"status": "inactive"})

        self._assign_martin_transfer_user()

    @api.model
    def get_haidly_qualification_profile(self):
        unified = self.env.ref(
            "doorway_agents_dashboard.agent_haidly",
            raise_if_not_found=False,
        )
        if unified and unified.status == "active":
            return unified
        return self.sudo().search(
            [
                ("haidly_agent_role", "=", "j0_qualification"),
                ("status", "=", "active"),
            ],
            limit=1,
        )

    @api.model
    def _post_init_haidly(self):
        Profile = self.sudo()
        role_xmlids = (
            ("j0_qualification", "agent_haidly", "Haidly · J+0 Qualification"),
            ("j1_relance", "agent_haidly_relance_j1", "Haidly · J+1 Relance"),
            ("j3_relance", "agent_haidly_relance_j3", "Haidly · J+3 Relance"),
            ("j7_relance", "agent_haidly_relance_j7", "Haidly · J+7 Fermeture"),
            ("j14_relance", "agent_haidly_relance_j14", "Haidly · J+14 Re-engagement"),
        )
        canonical_ids = set()
        unified = None
        for role, xmlid, display_name in role_xmlids:
            rec = self.env.ref(
                "doorway_agents_dashboard.%s" % xmlid,
                raise_if_not_found=False,
            )
            if not rec:
                continue
            canonical_ids.add(rec.id)
            if role == "j0_qualification":
                unified = rec
            vals = {"haidly_agent_role": role, "name": display_name}
            if role == "j0_qualification":
                vals.update(
                    {
                        "provider": "elevenlabs",
                        "pipeline": "renovation",
                        "default_volet": "qualification",
                        "agent_type": "outbound",
                        "status": "active",
                        "transfer_phone": "+14389929200",
                    }
                )
            elif role != "j0_qualification":
                vals.setdefault("status", "inactive")
            rec.write(vals)

        if unified:
            phone = self.env.ref(
                "doorway_agents_dashboard.agent_haidly_phone",
                raise_if_not_found=False,
            )
            if phone:
                unified.write({"default_phone_number_id": phone.id})

        haidly_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly")
            or ""
        ).strip()
        if haidly_id and unified:
            dupes = Profile.search(
                [
                    ("external_agent_id", "=", haidly_id),
                    ("id", "!=", unified.id),
                    ("status", "=", "active"),
                ]
            )
            if dupes:
                dupes.write({"status": "inactive"})

        self._assign_martin_transfer_user()
