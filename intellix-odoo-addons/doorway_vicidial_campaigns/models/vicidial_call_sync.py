# -*- coding: utf-8 -*-
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"INCALL", "QUEUE"})


class VicidialCallSync(models.Model):
    _name = "doorway.vicidial.call.sync"
    _description = "Sync appel VICIdial temps réel"
    _order = "date_debut desc"

    vicidial_call_id = fields.Char("ID appel VICIdial", index=True)
    vicidial_agent_id = fields.Char("Agent VICIdial")
    employee_id = fields.Many2one("hr.employee", string="Agent Odoo")
    user_id = fields.Many2one("res.users", string="Utilisateur Odoo", index=True)

    phone = fields.Char("Téléphone appelé")
    phone_normalized = fields.Char("Téléphone normalisé", index=True)
    lead_name = fields.Char("Nom contact")
    vicidial_list_id = fields.Char("Liste VICIdial")
    campagne_vicidial = fields.Char("Campagne VICIdial")

    statut_vicidial = fields.Selection(
        [
            ("INCALL", "En appel"),
            ("PAUSED", "En pause"),
            ("DISPO", "Disponible"),
            ("HUNG_UP", "Appel terminé"),
        ]
    )
    date_debut = fields.Datetime("Début appel")
    date_fin = fields.Datetime("Fin appel")
    duree_secondes = fields.Integer("Durée (s)")

    lead_id = fields.Many2one("crm.lead", string="Lead CRM", index=True)
    lead_ouvert = fields.Boolean("Lead ouvert dans browser", default=False)
    qualification_faite = fields.Boolean(default=False)

    @api.model
    def _normalize_phone(self, phone):
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) > 10:
            digits = digits[-10:]
        return digits

    @api.model
    def _agent_info_from_record(self, agent, icp=None):
        icp = icp or self.env["ir.config_parameter"].sudo()
        user = agent.user_id
        employee = user.employee_id if user else self.env["hr.employee"]
        return {
            "vicidial_user": (agent.vicidial_user or "").strip(),
            "employee_id": employee.id if employee else False,
            "user_id": user.id,
            "team_id": int(
                agent.vicidial_crm_team_id.id
                or icp.get_param("doorway.vicidial_default_team_id")
                or 0
            ),
            "stage_id": int(
                agent.vicidial_crm_stage_id.id
                or icp.get_param("doorway.vicidial_default_stage_id")
                or 0
            ),
        }

    @api.model
    def _get_agents_odoo_vicidial(self):
        """Tous les agents VICIdial avec qualification CRM active."""
        icp = self.env["ir.config_parameter"].sudo()
        agents = self.env["doorway.campaign.agent.user"].sudo().search(
            [
                ("active", "=", True),
                ("vicidial_qualification_active", "=", True),
                ("user_id", "!=", False),
                ("vicidial_user", "!=", False),
            ]
        )
        return [
            self._agent_info_from_record(agent, icp)
            for agent in agents
            if agent.vicidial_user
        ]

    @api.model
    def _get_agent_for_user(self, user):
        user = user.sudo()
        Session = self.env["doorway.vicidial.agent.session"].sudo()
        active = Session.get_active_session(user)
        Agent = self.env["doorway.campaign.agent.user"]
        domain = [
            ("user_id", "=", user.id),
            ("active", "=", True),
            ("vicidial_qualification_active", "=", True),
        ]
        if active and active.vicidial_user:
            agent = Agent.search(
                domain + [("vicidial_user", "=", active.vicidial_user)], limit=1
            )
            if agent:
                return self._agent_info_from_record(agent)
        agent = Agent.search(domain, order="id desc", limit=1)
        if not agent or not agent.vicidial_user:
            return None
        return self._agent_info_from_record(agent)

    @api.model
    def _run_setup_vicidial_qualification(self):
        from odoo.addons.doorway_vicidial_campaigns.hooks import (
            _setup_vicidial_qualification_agents,
        )

        _setup_vicidial_qualification_agents(self.env)
        return True

    @api.model
    def sync_depuis_vicidial(self):
        """Cron : sync tous les agents VICIdial."""
        for agent in self._get_agents_odoo_vicidial():
            self._sync_agent(agent, notify=False)
        return True

    @api.model
    def sync_for_current_user(self):
        """Polling JS : sync l'agent connecté uniquement."""
        agent = self._get_agent_for_user(self.env.user)
        if not agent:
            return {"event": "idle", "reason": "no_vicidial_profile"}
        return self._sync_agent(agent, notify=True)

    @api.model
    def register_manual_outbound(
        self, user, vicidial_user, campaign, phone_number, lead_id=None
    ):
        """Enregistre un appel manuel dans l'historique hub (sync temps réel)."""
        user = user.sudo()
        campaign = campaign.sudo()
        agent_info = self._get_agent_for_user(user)
        if not agent_info:
            agent_info = {
                "vicidial_user": (vicidial_user or "").strip(),
                "user_id": user.id,
                "employee_id": user.employee_id.id if user.employee_id else False,
                "team_id": 0,
                "stage_id": 0,
            }
        phone = (phone_number or "").strip()
        active = self.search(
            [
                ("user_id", "=", user.id),
                ("statut_vicidial", "=", "INCALL"),
                ("date_fin", "=", False),
            ],
            limit=1,
        )
        if active:
            active._marquer_termine(notify=False)
        call_data = {
            "user": vicidial_user,
            "campaign_id": campaign.vicidial_campaign_id or "",
            "lead_id": lead_id or "",
            "phone_number": phone,
            "list_id": "",
        }
        lead = self._trouver_ou_creer_lead(call_data, agent_info, phone)
        call_uid = "manual-%s-%s" % (
            (vicidial_user or "agent"),
            fields.Datetime.now().strftime("%Y%m%d%H%M%S"),
        )
        sync = self.create(
            {
                "vicidial_call_id": call_uid,
                "vicidial_agent_id": vicidial_user,
                "employee_id": agent_info.get("employee_id") or False,
                "user_id": user.id,
                "phone": phone,
                "phone_normalized": self._normalize_phone(phone),
                "lead_name": lead.name,
                "campagne_vicidial": campaign.vicidial_campaign_id or "",
                "statut_vicidial": "INCALL",
                "date_debut": fields.Datetime.now(),
                "lead_id": lead.id,
                "lead_ouvert": True,
            }
        )
        self._link_call_log_to_lead(call_uid, lead)
        return sync

    @api.model
    def _fetch_live_call(self, vicidial_user):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        if not svc.is_available():
            return None
        conn = svc._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    vla.user,
                    vla.status,
                    vla.lead_id,
                    vla.campaign_id,
                    vla.uniqueid,
                    vla.callerid,
                    vla.last_call_time,
                    vl.first_name,
                    vl.last_name,
                    vl.phone_number,
                    vl.email,
                    vl.address1,
                    vl.city,
                    vl.list_id
                FROM vicidial_live_agents vla
                LEFT JOIN vicidial_list vl ON vla.lead_id = vl.lead_id
                WHERE vla.user = %s
                  AND vla.status IN ('INCALL', 'QUEUE')
                LIMIT 1
                """,
                (vicidial_user,),
            )
            row = cur.fetchone()
            cur.close()
            return row
        finally:
            conn.close()

    @api.model
    def _sync_agent(self, agent_info, notify=False):
        live = self._fetch_live_call(agent_info["vicidial_user"])
        active_sync = self.search(
            [
                ("user_id", "=", agent_info["user_id"]),
                ("statut_vicidial", "=", "INCALL"),
                ("date_fin", "=", False),
            ],
            limit=1,
            order="date_debut desc",
        )

        if live:
            return self._handle_active_call(live, agent_info, active_sync, notify)

        if active_sync:
            active_sync._marquer_termine(notify=notify)
            return {
                "event": "call_ended",
                "lead_id": active_sync.lead_id.id if active_sync.lead_id else False,
            }
        return {"event": "idle"}

    def _handle_active_call(self, call_data, agent_info, active_sync, notify):
        phone = call_data.get("phone_number") or call_data.get("callerid") or ""
        call_uid = (
            call_data.get("uniqueid")
            or "%s-%s" % (call_data.get("user"), call_data.get("lead_id") or phone)
        )

        if active_sync and active_sync.vicidial_call_id == str(call_uid):
            return self._payload_open(active_sync, notify=False)

        if active_sync:
            active_sync._marquer_termine(notify=False)

        lead = self._trouver_ou_creer_lead(call_data, agent_info, phone)
        sync = self.create(
            {
                "vicidial_call_id": str(call_uid),
                "vicidial_agent_id": call_data["user"],
                "employee_id": agent_info["employee_id"],
                "user_id": agent_info["user_id"],
                "phone": phone,
                "phone_normalized": self._normalize_phone(phone),
                "lead_name": lead.name,
                "campagne_vicidial": call_data.get("campaign_id", ""),
                "vicidial_list_id": str(call_data.get("list_id") or ""),
                "statut_vicidial": "INCALL",
                "date_debut": fields.Datetime.now(),
                "lead_id": lead.id,
                "lead_ouvert": True,
            }
        )
        lead.write(
            {
                "source_vicidial": True,
                "vicidial_call_uid": str(call_uid),
                "campagne_vicidial": call_data.get("campaign_id", ""),
            }
        )
        self._link_call_log_to_lead(str(call_uid), lead)
        _logger.info(
            "VICIdial sync: lead %s ouvert pour %s (appel %s)",
            lead.name,
            call_data["user"],
            call_uid,
        )
        return self._payload_open(sync, notify=notify)

    def _payload_open(self, sync, notify=False):
        view = self.env.ref(
            "doorway_vicidial_campaigns.view_crm_lead_vicidial_qualification_form",
            raise_if_not_found=False,
        )
        payload = {
            "event": "lead_open",
            "lead_id": sync.lead_id.id,
            "lead_name": sync.lead_id.name,
            "phone": sync.phone or "",
            "call_uid": sync.vicidial_call_id,
            "view_id": view.id if view else False,
        }
        if notify and sync.user_id:
            self.env["bus.bus"]._sendone(
                sync.user_id.partner_id,
                "doorway/vicidial/lead_open",
                payload,
            )
        return payload

    @api.model
    def _team_id_for_vicidial_campaign(self, campaign_id):
        """Pipeline CRM imposé par campagne VICIdial (ex. DW_FRB2C → Rénovation)."""
        from odoo.addons.doorway_vicidial_campaigns.models.campaign_operational import (
            PIPELINE_BY_VICIDIAL,
        )

        pipeline = PIPELINE_BY_VICIDIAL.get((campaign_id or "").strip().upper())
        if not pipeline:
            return False
        label = {
            "renovation": "Rénovation",
            "driven": "Driven",
            "marketing": "Marketing",
        }.get(pipeline, pipeline)
        team = self.env["crm.team"].sudo().search(
            [("name", "ilike", label)], limit=1
        )
        return team.id if team else False

    def _trouver_ou_creer_lead(self, call_data, agent_info, phone):
        Lead = self.env["crm.lead"].sudo()
        Session = self.env["doorway.vicidial.agent.session"].sudo()
        partner, lead = Session._resolve_contact_records(phone=phone)
        normalized = self._normalize_phone(phone)
        if not lead and normalized:
            tail = normalized[-9:]
            LeadModel = Lead
            phone_fields = ["phone"]
            if "mobile" in LeadModel._fields:
                phone_fields.append("mobile")
            if len(phone_fields) == 1:
                domain = [("active", "=", True), ("phone", "ilike", tail)]
            else:
                domain = [
                    ("active", "=", True),
                    "|",
                    ("phone", "ilike", tail),
                    ("mobile", "ilike", tail),
                ]
            lead = Lead.search(domain, limit=1)
        nom = (
            "%s %s"
            % (
                call_data.get("first_name") or "",
                call_data.get("last_name") or "",
            )
        ).strip()
        if not nom and partner:
            nom = partner.name
        if not nom:
            nom = _("Contact — %s") % (phone or _("inconnu"))

        team_id = agent_info.get("team_id") or False
        campaign = (call_data.get("campaign_id") or "").strip().upper()
        campaign_team = self._team_id_for_vicidial_campaign(campaign)
        if campaign_team:
            team_id = campaign_team
        stage_id = agent_info.get("stage_id") or False
        tag_ids = self._get_default_tags()

        if lead:
            vals = {"user_id": agent_info["user_id"], "source_vicidial": True}
            keep_team = (lead.name or "").startswith("Léa —") or any(
                "Transfert chaud" in (t.name or "") for t in lead.tag_ids
            )
            if team_id and not keep_team:
                vals["team_id"] = team_id
            if campaign:
                vals["campagne_vicidial"] = campaign
            lead.write(vals)
            return lead

        return Lead.create(
            {
                "name": nom,
                "phone": phone,
                "partner_id": partner.id if partner else False,
                "email_from": call_data.get("email") or (partner.email if partner else ""),
                "street": call_data.get("address1") or "",
                "city": call_data.get("city") or "",
                "user_id": agent_info["user_id"],
                "team_id": team_id or False,
                "stage_id": stage_id or False,
                "type": "lead",
                "source_vicidial": True,
                "campagne_vicidial": campaign or False,
                "description": _("Appel VICIdial — campagne %s")
                % (call_data.get("campaign_id") or ""),
                "tag_ids": [(6, 0, tag_ids)] if tag_ids else False,
            }
        )

    def _create_coaching_call(self, duree):
        self.ensure_one()
        Coaching = self.env.get("pe.coaching.call")
        employee = self._resolve_employee_for_user(self.user_id)
        if not Coaching or not employee:
            return
        existing = Coaching.sudo().search(
            [("vicidial_call_id", "=", self.vicidial_call_id)], limit=1
        )
        if existing:
            return
        recording = self._fetch_recording_url()
        qual = (
            self.lead_id.qualification_statut
            if self.lead_id
            else "non_fait"
        )
        vals = {
            "employee_id": employee.id,
            "date_appel": self.date_debut or fields.Datetime.now(),
            "source": "vicidial",
            "vicidial_call_id": self.vicidial_call_id,
            "duree_secondes": duree,
            "numero_appele": self.phone,
            "lead_id": self.lead_id.id if self.lead_id else False,
            "audio_url": recording,
        }
        if "qualification_appel" in Coaching._fields:
            vals["qualification_appel"] = qual
        Coaching.sudo().create(vals)

    def _link_call_log_to_lead(self, vicidial_call_id, lead):
        if not vicidial_call_id or not lead:
            return
        log = self.env["doorway.call.log"].sudo().search(
            [("vicidial_call_id", "=", vicidial_call_id)], limit=1
        )
        if log and not log.lead_id:
            log.write({"lead_id": lead.id})
        elif not log and lead.phone:
            log = self.env["doorway.call.log"].sudo().search(
                [("phone_number", "=", lead.phone), ("lead_id", "=", False)],
                order="call_date desc",
                limit=1,
            )
            if log:
                log.write({"lead_id": lead.id})

    @api.model
    def _resolve_employee_for_user(self, user):
        user = user.sudo()
        if user.employee_id:
            return user.employee_id
        Profile = self.env.get("pe.employee.profile")
        if not Profile:
            return self.env["hr.employee"]
        profile = Profile.sudo().search(
            [("employee_id.user_id", "=", user.id)], limit=1
        )
        if not profile:
            agent = self.env["doorway.campaign.agent.user"].sudo().search(
                [("user_id", "=", user.id)], limit=1
            )
            if agent and agent.vicidial_user:
                profile = Profile.sudo().search(
                    [
                        "|",
                        ("vicidial_user", "=", agent.vicidial_user),
                        ("vicidial_agent_id", "=", agent.vicidial_user),
                    ],
                    limit=1,
                )
        if profile:
            employee = profile.sudo().employee_id
            if employee:
                return employee
            return self.env["hr.employee"].sudo().search(
                [("user_id", "=", user.id), ("active", "=", True)],
                limit=1,
            )
        return self.env["hr.employee"]

    def _fetch_recording_url(self):
        self.ensure_one()
        if not self.vicidial_call_id:
            return False
        log = self.env["doorway.call.log"].sudo().search(
            [("vicidial_call_id", "=", self.vicidial_call_id)], limit=1
        )
        return log.recording_url if log else False

    @api.model
    def _get_default_tags(self):
        return self.env["crm.tag"].sudo().search(
            [("name", "in", ["Appels", "VICIdial", "France", "À qualifier"])]
        ).ids

    def _marquer_termine(self, notify=False):
        self.ensure_one()
        now = fields.Datetime.now()
        duree = 0
        if self.date_debut:
            duree = int((now - self.date_debut).total_seconds())
        self.write(
            {
                "statut_vicidial": "HUNG_UP",
                "date_fin": now,
                "duree_secondes": duree,
                "lead_ouvert": False,
            }
        )
        session = self.env["doorway.vicidial.agent.session"].get_active_session(
            self.user_id
        )
        if session:
            session.record_call_event(
                qualification_faite=self.qualification_faite,
                is_rappel=bool(
                    self.lead_id
                    and self.lead_id.qualification_statut == "a_rappeler"
                ),
            )
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            VicidialService(self.env(su=True)).upsert_call_from_vicidial_sync(self)
        except Exception:
            _logger.exception(
                "Upsert call log failed for VICIdial sync %s", self.vicidial_call_id
            )
        self._create_coaching_call(duree)
        if self.lead_id and not self.qualification_faite:
            model = self.env["ir.model"]._get("crm.lead")
            assignee = self.lead_id._rappel_assignee_id()
            self.env["mail.activity"].sudo().create(
                {
                    "res_model_id": model.id,
                    "res_id": self.lead_id.id,
                    "user_id": assignee,
                    "summary": _("Rappeler — pas encore qualifié"),
                    "note": _(
                        "<p>Appel terminé sans qualification complète.</p>"
                    ),
                    "date_deadline": fields.Date.today() + timedelta(days=1),
                }
            )
        if notify and self.user_id:
            self.env["bus.bus"]._sendone(
                self.user_id.partner_id,
                "doorway/vicidial/call_ended",
                {"lead_id": self.lead_id.id if self.lead_id else False},
            )
