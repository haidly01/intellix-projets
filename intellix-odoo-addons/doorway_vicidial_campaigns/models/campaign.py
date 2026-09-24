# -*- coding: utf-8 -*-
import logging
import re
import threading

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwayCampaign(models.Model):
    _name = "doorway.campaign"
    _description = "Campagne d'appels — Doorway"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Nom campagne", required=True, tracking=True)
    campaign_mode = fields.Selection(
        [
            ("ia_agent", "Agent IA uniquement"),
            ("human_agent", "Agent humain uniquement"),
            ("mixed", "Mixte (IA + transfert humain)"),
        ],
        string="Mode",
        required=True,
        default="ia_agent",
        tracking=True,
    )
    pipeline = fields.Selection(
        [
            ("renovation", "Rénovation"),
            ("immobilier", "Immobilier"),
            ("toitures", "Soumission Toitures"),
            ("thermopompe", "Ici Thermopompe"),
            ("driven", "Driven (B2B)"),
            ("itex", "ITEX Québec"),
            ("coins_quebec", "Coins Québec"),
            ("assurance", "Assurance"),
            ("marketing", "Marketing"),
        ],
        string="Pipeline",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("ready", "Prêt"),
            ("active", "Actif"),
            ("paused", "Pause"),
            ("completed", "Terminé"),
            ("cancelled", "Annulé"),
        ],
        string="Statut",
        default="draft",
        tracking=True,
    )
    date_start = fields.Datetime(string="Début programmé")
    date_end = fields.Datetime(string="Fin automatique")
    description = fields.Text(string="Notes internes")

    ia_agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA principal",
        domain="[('status', '=', 'active')]",
    )
    ia_fallback_agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA secours",
    )
    ia_call_script_hint = fields.Text(string="Contexte additionnel pour l'agent IA")
    ia_max_call_duration = fields.Integer(
        string="Durée max appel IA (sec)", default=180
    )
    ia_transfer_on_interest = fields.Boolean(
        string="Transférer vers humain si lead chaud", default=False
    )
    ia_transfer_number = fields.Char(string="Numéro de transfert")

    human_agent_ids = fields.Many2many(
        "doorway.campaign.agent.user",
        "campaign_human_agent_rel",
        "campaign_id",
        "agent_id",
        string="Agents humains",
        help="Comptes VICIdial liés (synchronisés depuis les utilisateurs assignés).",
    )
    human_agent_user_ids = fields.Many2many(
        "res.users",
        "campaign_human_agent_user_rel",
        "campaign_id",
        "user_id",
        string="Agents humains assignés",
        help="Utilisateurs Odoo autorisés sur cette campagne. "
        "Leur compte VICIdial est créé ou mis à jour automatiquement.",
        domain="[('is_human_call_agent', '=', True)]",
    )
    vicidial_campaign_id = fields.Char(
        string="ID campagne VICIdial", readonly=True, copy=False
    )
    vicidial_list_id = fields.Char(string="ID liste VICIdial", readonly=True)
    vicidial_ingroup = fields.Char(
        string="In-Group VICIdial",
        help="Référence technique VICIdial. "
        "L'assignation des agents se fait via les utilisateurs Odoo.",
    )
    script_url = fields.Char(string="URL script agent")

    amd_enabled = fields.Boolean(string="Détection répondeur (AMD)", default=True)
    amd_action = fields.Selection(
        [
            ("leave_message", "Laisser un message"),
            ("hangup", "Raccrocher"),
            ("callback_schedule", "Programmer rappel"),
        ],
        string="Action si répondeur",
        default="leave_message",
    )
    amd_message_tts = fields.Text(string="Message répondeur (texte TTS)")
    amd_message_file = fields.Char(string="Fichier audio répondeur (chemin serveur)")
    amd_wait_seconds = fields.Integer(string="Délai analyse AMD (sec)", default=3)
    amd_sensitivity = fields.Selection(
        [
            ("low", "Faible"),
            ("medium", "Moyen"),
            ("high", "Élevé"),
        ],
        string="Sensibilité AMD",
        default="medium",
    )
    amd_callback_delay_hours = fields.Integer(
        string="Délai rappel AMD (heures)", default=24
    )

    max_concurrent_calls = fields.Integer(
        string="Appels simultanés max", default=10, required=True
    )
    dial_ratio = fields.Float(string="Ratio numérotation / agents", default=1.5)
    dial_level = fields.Integer(string="Dial level VICIdial", default=1)
    dial_timeout_seconds = fields.Integer(
        string="Timeout sans réponse (sec)", default=30
    )
    calls_per_minute_limit = fields.Integer(
        string="Limite appels / minute", default=60
    )
    auto_dial_mode = fields.Selection(
        [
            ("preview", "Preview (manuel)"),
            ("progressive", "Progressive"),
            ("predictive", "Predictive (auto)"),
        ],
        string="Mode numérotation",
        default="progressive",
    )
    retry_attempts = fields.Integer(string="Tentatives de rappel", default=2)
    retry_delay_minutes = fields.Integer(
        string="Délai entre tentatives (min)", default=60
    )

    contact_ids = fields.One2many(
        "doorway.campaign.contact", "campaign_id", string="Contacts"
    )
    call_log_ids = fields.One2many(
        "doorway.call.log", "campaign_id", string="Log appels"
    )
    total_contacts = fields.Integer(
        string="Total contacts", compute="_compute_stats", store=True
    )
    total_called = fields.Integer(
        string="Appelés", compute="_compute_stats", store=True
    )
    total_answered = fields.Integer(
        string="Réponses humaines", compute="_compute_stats", store=True
    )
    total_amd = fields.Integer(
        string="Répondeurs", compute="_compute_stats", store=True
    )
    answer_rate = fields.Float(
        string="Taux réponse %", compute="_compute_stats", store=True
    )

    @api.depends(
        "contact_ids",
        "call_log_ids",
        "call_log_ids.amd_result",
    )
    def _compute_stats(self):
        CallLog = self.env["doorway.call.log"]
        Contact = self.env["doorway.campaign.contact"]
        for rec in self:
            rec.total_contacts = Contact.search_count(
                [("campaign_id", "=", rec.id)]
            )
            rec.total_called = CallLog.search_count(
                [("campaign_id", "=", rec.id)]
            )
            rec.total_answered = CallLog.search_count(
                [
                    ("campaign_id", "=", rec.id),
                    ("amd_result", "=", "human"),
                ]
            )
            rec.total_amd = CallLog.search_count(
                [
                    ("campaign_id", "=", rec.id),
                    "|",
                    ("amd_result", "in", ("answering_machine", "amd_hangup")),
                    ("disposition", "=", "REPONDEUR"),
                ]
            )
            rec.answer_rate = (
                (rec.total_answered / rec.total_called * 100.0)
                if rec.total_called
                else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any("human_agent_user_ids" in vals for vals in vals_list):
            records._sync_human_agents_from_users()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "human_agent_user_ids" in vals:
            self._sync_human_agents_from_users()
        return res

    def _sync_human_agents_from_users(self, sync_vicidial=None):
        """Crée ou met à jour doorway.campaign.agent.user depuis human_agent_user_ids."""
        Agent = self.env["doorway.campaign.agent.user"]
        user_group = self.env.context.get("human_agent_user_group", "AGENTS")
        user_level = self.env.context.get("human_agent_user_level", 1)
        if sync_vicidial is None:
            sync_vicidial = self.env.context.get("sync_human_agent_vicidial", True)

        for rec in self:
            linked = Agent.browse()
            for user in rec.human_agent_user_ids:
                login = Agent._vicidial_login_for_user(user)
                agent = Agent.search([("vicidial_user", "=", login)], limit=1)
                vals = {
                    "user_id": user.id,
                    "vicidial_user": login,
                    "full_name": user.name,
                    "user_group": user_group,
                    "user_level": user_level,
                    "active": True,
                }
                if agent:
                    agent.write(vals)
                else:
                    agent = Agent.create(vals)
                linked |= agent
            rec.human_agent_ids = [(6, 0, linked.ids)]
            if sync_vicidial and linked:
                linked.action_sync_vicidial()
            rec._sync_vicidial_campaign_agents()

    def _sync_vicidial_campaign_agents(self):
        """Ajoute les agents assignés dans vicidial_campaign_agents (MySQL)."""
        for rec in self:
            cid = (rec.vicidial_campaign_id or "").strip()[:20]
            if not cid or not rec.human_agent_ids:
                continue
            svc = rec._vicidial_svc()
            if not svc.is_available():
                continue
            logins = [
                (a.vicidial_user or "").strip()[:20]
                for a in rec.human_agent_ids
                if (a.vicidial_user or "").strip()
            ]
            if not logins:
                continue
            conn = svc._connect()
            try:
                cur = conn.cursor()
                for login in logins:
                    cur.execute(
                        """
                        SELECT 1 FROM vicidial_campaign_agents
                        WHERE user = %s AND campaign_id = %s LIMIT 1
                        """,
                        (login, cid),
                    )
                    if not cur.fetchone():
                        cur.execute(
                            """
                            INSERT INTO vicidial_campaign_agents (
                                user, campaign_id, campaign_rank,
                                campaign_weight, campaign_grade
                            ) VALUES (%s, %s, 1, 10, 1)
                            """,
                            (login, cid),
                        )
                    cur.execute(
                        """
                        UPDATE vicidial_users
                        SET change_agent_campaign = '1'
                        WHERE user = %s AND change_agent_campaign = '0'
                        """,
                        (login,),
                    )
                conn.commit()
                cur.close()
            finally:
                conn.close()

    def _vicidial_svc(self):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        return VicidialService(self.env)

    def action_start(self):
        self.ensure_one()
        if not self.vicidial_campaign_id:
            self._create_vicidial_campaign()
        svc = self._vicidial_svc()
        if not svc.is_available():
            raise UserError(_("VICIdial MySQL indisponible."))
        svc.start_campaign(self.vicidial_campaign_id)
        if self.campaign_mode == "ia_agent" and self.vicidial_campaign_id:
            svc.ensure_ia_remote_agent(self.vicidial_campaign_id)
            cid = (self.vicidial_campaign_id or "")[:8]
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                QC_IA_CAMPAIGN_IDS,
            )

            if (
                cid.startswith("DW_ES")
                or cid.startswith("DWTO")
                or cid in ("ABD_DEMO",)
            ):
                svc.ensure_spain_outbound_dialing(self.vicidial_campaign_id)
            elif cid.startswith("DW_QC") or cid in QC_IA_CAMPAIGN_IDS or cid == "DW_RAPQC":
                svc.ensure_quebec_outbound_dialing(self.vicidial_campaign_id)
        self.state = "active"

    def action_pause(self):
        self.ensure_one()
        if self.vicidial_campaign_id:
            self._vicidial_svc().pause_campaign(self.vicidial_campaign_id)
        self.state = "paused"

    def action_stop(self):
        self.ensure_one()
        if self.vicidial_campaign_id:
            self._vicidial_svc().pause_campaign(self.vicidial_campaign_id)
        self.state = "completed"

    def action_set_ready(self):
        self.write({"state": "ready"})

    def action_update_concurrent(self, new_level):
        self.ensure_one()
        level = int(new_level)
        self._vicidial_svc().update_campaign_dial_level(
            self.vicidial_campaign_id, level
        )
        self.dial_level = level
        return True

    def _create_vicidial_campaign(self):
        self.ensure_one()
        svc = self._vicidial_svc()
        if not svc.is_available():
            raise UserError(_("VICIdial MySQL indisponible."))
        result = svc.create_campaign_from_record(self)
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Échec création VICIdial."))
        self.write(
            {
                "vicidial_campaign_id": result.get("campaign_id"),
                "vicidial_list_id": result.get("list_id"),
                "state": "ready",
            }
        )

    def action_sync_vicidial(self):
        """Met à jour la config VICIdial sans démarrer."""
        for rec in self:
            if not rec.vicidial_campaign_id:
                rec._create_vicidial_campaign()
            else:
                rec._vicidial_svc().sync_campaign_record(rec)
        return True

    def _phone_import_country(self):
        """Pays par défaut pour normaliser les numéros à l'import."""
        self.ensure_one()
        name = (self.name or "").lower()
        if any(
            hint in name
            for hint in (
                "espagne",
                "spain",
                "españa",
                "sofía",
                "sofia",
                "avatrade",
                "salamanca",
                "iso esp",
            )
        ):
            return "ES"
        if any(hint in name for hint in ("quebec", "québec", "canada")):
            return "CA"
        return "FR"

    def action_open_import_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Importer contacts"),
            "res_model": "doorway.file.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_campaign_id": self.id},
        }

    def action_cleanup_list(self):
        self.ensure_one()
        stats = self._vicidial_svc().cleanup_campaign_list(self)
        body = _(
            "Liste nettoyée : %(kept)s conservés, %(normalized)s normalisés, "
            "%(removed)s supprimés (%(dupes)s doublons). Hopper : %(hopper)s."
        ) % {
            "kept": stats.get("kept", 0),
            "normalized": stats.get("normalized", 0),
            "removed": stats.get("removed", 0),
            "dupes": stats.get("dupes_removed", 0),
            "hopper": stats.get("hopper", 0),
        }
        self.message_post(body=body, message_type="notification")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Liste nettoyée"),
                "message": body,
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_user_config(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Configurer agents"),
            "res_model": "doorway.user.config.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_campaign_id": self.id},
        }

    def action_get_live_stats(self):
        self.ensure_one()
        if not self.vicidial_campaign_id:
            return {}
        return self._vicidial_svc().get_live_stats(self)

    @api.model
    def action_get_monitor_dashboard(self):
        """Données tableau de bord live — un seul appel RPC (évite N× polling)."""
        campaigns = self.search([], order="name")
        live_map = self._vicidial_svc().get_live_stats_batch(campaigns)
        rows = []
        for c in campaigns:
            live = live_map.get(c.id, {})
            rows.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "vicidial_campaign_id": c.vicidial_campaign_id,
                    "campaign_mode": c.campaign_mode,
                    "state": c.state,
                    "operational_label": c.operational_label,
                    "dial_site": c.dial_site,
                    "is_dialing_prod": c.is_dialing_prod,
                    "vicidial_adl": c.vicidial_adl,
                    "total_contacts": c.total_contacts,
                    "total_called": c.total_called,
                    "total_answered": c.total_answered,
                    "total_amd": c.total_amd,
                    "answer_rate": c.answer_rate,
                    "dial_level": c.dial_level,
                    "max_concurrent_calls": c.max_concurrent_calls,
                    "live_stats": live,
                }
            )
        return rows

    def action_view_call_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal appels"),
            "res_model": "doorway.call.log",
            "view_mode": "list,form",
            "domain": [("campaign_id", "=", self.id)],
            "context": {"default_campaign_id": self.id},
        }


    def _schedule_light_hostinger_sync(self, limit=15):
        """Sync Hostinger après ouverture console — thread détaché, ne bloque pas le worker."""
        self.ensure_one()
        hostinger_ids = self._hostinger_only_vicidial_ids()
        vid = (self.vicidial_campaign_id or "")[:8]
        if vid not in hostinger_ids:
            return
        dbname = self.env.cr.dbname
        campaign_id = self.id
        uid = self.env.uid

        def _worker():
            try:
                from odoo.modules.registry import Registry

                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, uid, {})
                    camp = env["doorway.campaign"].browse(campaign_id)
                    if not camp.exists():
                        return
                    camp._vicidial_svc().sync_hostinger_campaign_background(
                        camp, limit=limit
                    )
                    cr.commit()
            except Exception as exc:
                _logger.warning(
                    "background hostinger sync campaign=%s: %s",
                    campaign_id,
                    exc,
                )

        threading.Thread(
            target=_worker,
            daemon=True,
            name="hostinger-sync-%s" % campaign_id,
        ).start()

    def action_sync_call_logs(self):
        svc = self._vicidial_svc()
        limit = int(self.env.context.get("sync_limit") or 80)
        full = bool(self.env.context.get("sync_full"))
        for camp in self:
            vid = (camp.vicidial_campaign_id or "")[:8]
            if vid in self._hostinger_only_vicidial_ids():
                if full:
                    svc.pull_hostinger_recordings()
                svc.sync_call_logs(camp, limit=limit if not full else 400)
                svc.backfill_lea_recordings(
                    vid, limit=limit if not full else 400, fast_only=not full
                )
            else:
                svc.sync_call_logs(camp, limit=limit)
        return True

    @api.model
    def cron_sync_call_logs(self):
        svc = self._vicidial_svc()
        campaigns = self.search([("state", "in", ("active", "paused", "ready"))])
        svc.sync_call_logs(campaigns)
        for vicidial_id in ("DW_FRB2C", "ABD_DEMO"):
            try:
                svc.backfill_sofia_recordings(vicidial_id, limit=200)
            except Exception as exc:
                _logger.warning(
                    "sofia recordings backfill %s: %s", vicidial_id, exc
                )
        try:
            svc.pull_hostinger_recordings()
        except Exception as exc:
            _logger.warning("hostinger recordings pull: %s", exc)
        for vicidial_id in ("DW_QCB2C", "DW_QCB2B"):
            try:
                svc.sync_call_logs(
                    campaigns.filtered(
                        lambda c: (c.vicidial_campaign_id or "")[:8] == vicidial_id
                    ),
                    limit=400,
                )
                svc.backfill_lea_recordings(vicidial_id, limit=400, fast_only=True)
            except Exception as exc:
                _logger.warning(
                    "lea recordings backfill %s: %s", vicidial_id, exc
                )

    def action_open_vicidial_admin(self):
        """Journal appels Odoo — ouverture immédiate, sync Hostinger en arrière-plan."""
        self.ensure_one()
        self._schedule_light_hostinger_sync(limit=15)
        action = self.action_view_call_logs()
        ctx = dict(action.get("context") or {})
        vid = (self.vicidial_campaign_id or "")[:8]
        if vid in self._hostinger_only_vicidial_ids():
            ctx["search_default_last_7_days"] = 1
        else:
            ctx["search_default_today"] = 1
        action["context"] = ctx
        action["name"] = _("Console appels — %s") % (self.name or self.vicidial_campaign_id)
        return action

    @api.model
    def _generate_vicidial_id(self, name, pipeline=None):
        slug = re.sub(r"[^A-Z0-9]", "", (name or "CAMP")[:6].upper())
        pipe = (pipeline or "")[:2].upper()
        return ("DW%s%s" % (pipe, slug))[:8] or "DWDOORWY"


    @api.model
    def get_script_html(self, campaign_id):
        """Retourne le script HTML de la campagne VICIdial active."""
        try:
            campaign = self.browse(campaign_id)
            if not campaign or not campaign.vicidial_campaign_id:
                return '<p>Aucune campagne active.</p>'
            import pymysql
            from odoo.addons.doorway_vicidial_campaigns.models.vicidial_db import get_vicidial_connection
            conn = get_vicidial_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT vs.script_text FROM vicidial_campaigns vc
                LEFT JOIN vicidial_scripts vs ON vs.script_id = vc.campaign_script
                WHERE vc.campaign_id = %s
            """, (campaign.vicidial_campaign_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row and row[0]:
                return row[0]
            return '<p>Aucun script pour cette campagne.</p>'
        except Exception as e:
            return '<p>Erreur: %s</p>' % str(e)
    @api.model
    def _run_setup_rappel_quebec(self):
        from odoo.addons.doorway_vicidial_campaigns.hooks import setup_rappel_quebec_campaign

        return setup_rappel_quebec_campaign(self.env)
