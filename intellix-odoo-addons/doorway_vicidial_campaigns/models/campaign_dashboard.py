# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
import threading
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STATE_LABELS = {
    "draft": "Brouillon",
    "ready": "Prêt",
    "active": "Active",
    "paused": "En pause",
    "completed": "Terminée",
    "cancelled": "Annulée",
}

OP_STATUS_LABELS = {
    "success": "Succès",
    "callback": "Décroché – à relancer",
    "voicemail": "Messagerie",
    "error": "Erreur",
    "in_progress": "En cours",
}


class DoorwayCampaignDashboard(models.Model):
    _inherit = "doorway.campaign"

    success_count = fields.Integer(compute="_compute_dashboard_kpis", store=True)
    qualified_lead_count = fields.Integer(compute="_compute_dashboard_kpis", store=True)
    rdv_count = fields.Integer(compute="_compute_dashboard_kpis", store=True)
    success_rate = fields.Float(compute="_compute_dashboard_kpis", store=True)
    conversion_rate = fields.Float(compute="_compute_dashboard_kpis", store=True)

    @api.depends(
        "contact_ids",
        "contact_ids.operational_status",
        "contact_ids.crm_lead_id",
        "call_log_ids",
        "call_log_ids.disposition",
        "total_contacts",
        "total_answered",
    )
    def _compute_dashboard_kpis(self):
        Contact = self.env["doorway.campaign.contact"]
        CallLog = self.env["doorway.call.log"]
        for rec in self:
            rec.success_count = CallLog.search_count(
                [
                    ("campaign_id", "=", rec.id),
                    "|",
                    ("disposition", "in", ("VENTE", "INTERET")),
                    ("amd_result", "=", "human"),
                ]
            )
            rec.qualified_lead_count = Contact.search_count(
                [
                    ("campaign_id", "=", rec.id),
                    ("crm_lead_id", "!=", False),
                ]
            )
            rec.rdv_count = Contact.search_count(
                [
                    ("campaign_id", "=", rec.id),
                    ("crm_lead_id", "!=", False),
                    ("crm_lead_id.stage_id.name", "ilike", "rdv"),
                ]
            )
            rec.success_rate = (
                (rec.success_count / rec.total_called * 100.0)
                if rec.total_called
                else 0.0
            )
            rec.conversion_rate = (
                (rec.qualified_lead_count / rec.total_contacts * 100.0)
                if rec.total_contacts
                else 0.0
            )

    def _dashboard_svc(self):
        return self._vicidial_svc()

    def _n8n_relaunch_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "doorway_vicidial_campaigns.n8n_relaunch_webhook",
                "https://n8n.intellixcrm.com/webhook/intellix/relaunch",
            )
        )

    @api.model
    def _dashboard_period_bounds(self, filters=None):
        """Période d'analyse (défaut : 7 derniers jours)."""
        filters = filters or {}
        today = fields.Date.today()
        date_to = filters.get("date_to") or fields.Date.to_string(today)
        if filters.get("date_from"):
            date_from = filters["date_from"]
        elif filters.get("period") == "today":
            date_from = date_to
        elif filters.get("period") == "month":
            date_from = fields.Date.to_string(today.replace(day=1))
        else:
            date_from = fields.Date.to_string(today - timedelta(days=7))
        return date_from, date_to

    @api.model
    def _qual_stats_index(self, date_from, date_to):
        stats = self.env["crm.lead"].get_campaign_qualification_stats(
            date_from=date_from, date_to=date_to
        )
        return {row["vicidial_id"]: row for row in stats}

    @api.model
    def dashboard_list_campaigns(self, filters=None):
        """Liste campagnes avec KPIs performance pour la vue principale."""
        filters = filters or {}
        domain = []
        if filters.get("pipeline"):
            domain.append(("pipeline", "=", filters["pipeline"]))
        if filters.get("agent_id"):
            domain.append(("ia_agent_id", "=", int(filters["agent_id"])))
        if filters.get("state"):
            domain.append(("state", "=", filters["state"]))

        date_from, date_to = self._dashboard_period_bounds(filters)
        campaigns = self.search(domain, order="create_date desc")
        qual_by_vici = self._qual_stats_index(date_from, date_to)
        live_map = {}
        if campaigns:
            live_map = campaigns._vicidial_svc().get_live_stats_batch(campaigns)

        agents = self.env["doorway.agent.profile"].search_read(
            [("status", "=", "active")], ["id", "name"]
        )
        rows = []
        summary = {
            "active_campaigns": 0,
            "total_contacts": 0,
            "calls_period": 0,
            "qualified": 0,
            "rdv": 0,
            "rappels": 0,
            "live_agents": 0,
            "calls_today": 0,
        }
        for c in campaigns:
            vid = c.vicidial_campaign_id or ""
            qual = qual_by_vici.get(vid, {})
            live = live_map.get(c.id, {})
            calls_period = qual.get("total") or 0
            qualified = qual.get("qualified") or 0
            rdv = qual.get("rdv") or c.rdv_count
            rappels = qual.get("rappels") or 0
            live_agents = live.get("live_agents") or 0
            calls_today = live.get("total_calls") or c.total_called or 0
            qual_rate = (
                round(qualified / calls_period * 100.0, 1) if calls_period else 0.0
            )
            if c.state == "active":
                summary["active_campaigns"] += 1
            summary["total_contacts"] += c.total_contacts
            summary["calls_period"] += calls_period
            summary["qualified"] += qualified
            summary["rdv"] += rdv
            summary["rappels"] += rappels
            summary["live_agents"] += live_agents
            summary["calls_today"] += calls_today
            rows.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "pipeline": c.pipeline,
                    "state": c.state,
                    "state_label": STATE_LABELS.get(c.state, c.state),
                    "campaign_mode": c.campaign_mode,
                    "vicidial_campaign_id": vid,
                    "agent_id": c.ia_agent_id.id,
                    "agent_name": c.ia_agent_id.name or "—",
                    "human_agents": len(c.human_agent_ids),
                    "create_date": fields.Datetime.to_string(c.create_date),
                    "total_contacts": c.total_contacts,
                    "answer_rate": round(c.answer_rate, 1),
                    "success_rate": round(c.success_rate, 1),
                    "qualified_leads": c.qualified_lead_count,
                    "rdv_count": rdv,
                    "calls_period": calls_period,
                    "qualified_period": qualified,
                    "rappels_period": rappels,
                    "qualification_rate": qual_rate,
                    "live_agents": live_agents,
                    "calls_today": calls_today,
                }
            )
        return {
            "campaigns": rows,
            "agents": agents,
            "pipelines": self._pipeline_options(),
            "summary": summary,
            "period": {"date_from": date_from, "date_to": date_to},
        }

    @api.model
    def _pipeline_options(self):
        field = self.fields_get(["pipeline"])["pipeline"]
        return [
            {"value": v, "label": l}
            for v, l in field.get("selection", [])
        ]

    def _schedule_dashboard_call_log_sync(self, limit=20):
        """Sync logs léger en thread — ne bloque pas le dashboard."""
        self.ensure_one()
        if not self.vicidial_campaign_id:
            return
        dbname = self.env.cr.dbname
        campaign_id = self.id
        uid = self.env.uid
        vid = (self.vicidial_campaign_id or "")[:8]
        hostinger = vid in self._hostinger_only_vicidial_ids()

        def _worker():
            try:
                from odoo.modules.registry import Registry

                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, uid, {})
                    camp = env["doorway.campaign"].browse(campaign_id)
                    if not camp.exists():
                        return
                    svc = camp._vicidial_svc()
                    if hostinger:
                        svc.sync_hostinger_campaign_background(camp, limit=limit)
                    else:
                        svc.sync_call_logs(camp, limit=limit, fast=True)
                    cr.commit()
            except Exception as exc:
                _logger.warning("dashboard call log sync %s: %s", campaign_id, exc)

        threading.Thread(
            target=_worker,
            daemon=True,
            name="dashboard-sync-%s" % campaign_id,
        ).start()

    def dashboard_detail(self, filters=None, page=1, page_size=20):
        """Vue détaillée : KPIs, timeline, contacts paginés."""
        self.ensure_one()
        if self.vicidial_campaign_id and self.state in ("active", "paused", "ready"):
            self._schedule_dashboard_call_log_sync()
        filters = filters or {}
        contact_domain = [("campaign_id", "=", self.id)]
        if filters.get("operational_status"):
            contact_domain.append(
                ("operational_status", "=", filters["operational_status"])
            )
        if filters.get("ai_score_min"):
            contact_domain.append(("ai_score", ">=", float(filters["ai_score_min"])))
        if filters.get("ai_score_max"):
            contact_domain.append(("ai_score", "<=", float(filters["ai_score_max"])))
        if filters.get("date_from"):
            contact_domain.append(("last_attempt_date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            contact_domain.append(("last_attempt_date", "<=", filters["date_to"]))

        Contact = self.env["doorway.campaign.contact"]
        total = Contact.search_count(contact_domain)
        offset = max(0, (int(page) - 1) * int(page_size))
        contacts = Contact.search(
            contact_domain, order="last_attempt_date desc", limit=page_size, offset=offset
        )

        period = filters.get("timeline_period", "today")
        return {
            "campaign": self._dashboard_campaign_header(),
            "kpis": self._dashboard_detail_kpis(),
            "timeline": self.dashboard_timeline(period),
            "contacts": [c._dashboard_row() for c in contacts],
            "pagination": {
                "page": int(page),
                "page_size": int(page_size),
                "total": total,
                "pages": max(1, (total + int(page_size) - 1) // int(page_size)),
            },
        }

    def _dashboard_campaign_header(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "pipeline": self.pipeline,
            "state": self.state,
            "state_label": STATE_LABELS.get(self.state, self.state),
            "agent_name": self.ia_agent_id.name or "—",
            "create_date": fields.Datetime.to_string(self.create_date),
        }

    def _dashboard_detail_kpis(self):
        self.ensure_one()
        logs = self.call_log_ids
        human = len(logs.filtered(lambda l: l.amd_result == "human"))
        vm = len(
            logs.filtered(
                lambda l: l.amd_result in ("answering_machine", "amd_hangup")
            )
        )
        failed = len(logs) - human - vm
        today = fields.Date.today()
        date_from = fields.Date.to_string(today - timedelta(days=7))
        date_to = fields.Date.to_string(today)
        qual = {}
        if self.vicidial_campaign_id:
            qual = self._qual_stats_index(date_from, date_to).get(
                self.vicidial_campaign_id, {}
            )
        live = self._vicidial_svc().get_live_stats_batch(self).get(self.id, {})
        calls_period = qual.get("total") or 0
        qualified = qual.get("qualified") or 0
        return {
            "contact_rate": round(self.answer_rate, 1),
            "human_count": human,
            "voicemail_count": vm,
            "failed_count": max(0, failed),
            "success_rate": round(self.success_rate, 1),
            "conversion_rate": round(self.conversion_rate, 1),
            "qualified_leads": self.qualified_lead_count,
            "rdv_count": qual.get("rdv") or self.rdv_count,
            "total_contacts": self.total_contacts,
            "calls_period": calls_period,
            "qualified_period": qualified,
            "rappels_period": qual.get("rappels") or 0,
            "qualification_rate": round(qualified / calls_period * 100.0, 1)
            if calls_period
            else 0.0,
            "live_agents": live.get("live_agents") or 0,
            "calls_today": live.get("total_calls") or self.total_called or 0,
            "human_agents": len(self.human_agent_ids),
        }

    def dashboard_timeline(self, period="today"):
        """Appels par heure pour graphique barres."""
        self.ensure_one()
        now = fields.Datetime.now()
        if period == "yesterday":
            end = now.replace(hour=23, minute=59, second=59)
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        elif period == "week":
            start = now - timedelta(days=7)
            end = now
        else:
            start = now.replace(hour=0, minute=0, second=0)
            end = now

        logs = self.call_log_ids.filtered(
            lambda l: l.call_date and start <= l.call_date <= end
        )
        buckets = {h: 0 for h in range(24)}
        for log in logs:
            if log.call_date:
                buckets[log.call_date.hour] += 1
        return [{"hour": h, "count": buckets[h]} for h in range(24)]

    def dashboard_contact_drawer(self, contact_id):
        """Données drawer latéral pour un contact."""
        contact = self.env["doorway.campaign.contact"].browse(contact_id).exists()
        if not contact or contact.campaign_id.id != self.id:
            raise UserError(_("Contact introuvable."))
        return contact._dashboard_drawer_payload()

    def dashboard_relaunch(self, contact_ids, priority="high"):
        """Relance VICIdial + webhook n8n."""
        self.ensure_one()
        contacts = self.env["doorway.campaign.contact"].browse(contact_ids).exists()
        contacts = contacts.filtered(lambda c: c.campaign_id.id == self.id)
        if not contacts:
            raise UserError(_("Aucun contact sélectionné."))

        svc = self._dashboard_svc()
        vici_result = svc.relaunch_contacts_priority(
            self, contacts, priority=99 if priority == "high" else 50
        )

        n8n_payload = {
            "lead_ids": contacts.ids,
            "campaign_id": self.id,
            "vicidial_campaign_id": self.vicidial_campaign_id,
            "priority": priority,
            "phones": contacts.mapped("phone_number"),
        }
        n8n_ok = self._trigger_n8n_relaunch(n8n_payload)

        contacts.write({"state": "in_hopper"})
        return {
            "status": "ok",
            "relaunched": len(contacts),
            "vicidial": vici_result,
            "n8n": n8n_ok,
        }

    def _trigger_n8n_relaunch(self, payload):
        url = self._n8n_relaunch_url()
        if not url:
            return False
        try:
            resp = requests.post(url, json=payload, timeout=15)
            return resp.status_code < 400
        except Exception as exc:  # noqa: BLE001
            _logger.warning("n8n relaunch webhook: %s", exc)
            return False

    def dashboard_export_csv(self, contact_ids):
        """Export CSV des contacts sélectionnés."""
        self.ensure_one()
        contacts = self.env["doorway.campaign.contact"].browse(contact_ids).exists()
        contacts = contacts.filtered(lambda c: c.campaign_id.id == self.id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Nom",
                "Téléphone",
                "Email",
                "Statut",
                "Dernière tentative",
                "Durée (s)",
                "Score IA",
                "Note IA",
                "Agent",
            ]
        )
        for c in contacts:
            name = " ".join(
                p for p in (c.first_name, c.last_name) if p
            ).strip()
            writer.writerow(
                [
                    name,
                    c.phone_number or "",
                    c.email or "",
                    OP_STATUS_LABELS.get(c.operational_status, ""),
                    c.last_attempt_date or "",
                    c.last_duration or 0,
                    c.ai_score or "",
                    (c.ai_note or "")[:200],
                    c.ia_agent_id.name or "",
                ]
            )
        data = base64.b64encode(buf.getvalue().encode("utf-8-sig")).decode("ascii")
        return {
            "filename": "campagne_%s_contacts.csv" % self.id,
            "data": data,
            "mime": "text/csv",
        }

    def dashboard_push_crm(self, contact_ids):
        """Crée des leads Odoo pour les contacts sans fiche CRM."""
        self.ensure_one()
        Lead = self.env["crm.lead"]
        contacts = self.env["doorway.campaign.contact"].browse(contact_ids).exists()
        contacts = contacts.filtered(lambda c: c.campaign_id.id == self.id)
        created = []
        for c in contacts:
            if c.crm_lead_id:
                continue
            name = " ".join(p for p in (c.first_name, c.last_name) if p).strip()
            lead = Lead.create(
                {
                    "name": name or ("Lead %s" % (c.phone_number or "")),
                    "contact_name": name,
                    "phone": c.phone_number,
                    "email_from": c.email,
                    "description": _("Import campagne %s") % self.name,
                    "type": "opportunity",
                }
            )
            c.crm_lead_id = lead.id
            created.append(lead.id)
        return {"created": created, "count": len(created)}

    def action_open_dashboard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "campaign_dashboard_action",
            "context": {"default_campaign_id": self.id},
        }

    @api.model
    def action_open_campaign_dashboard(self):
        return {
            "type": "ir.actions.client",
            "tag": "campaign_dashboard_action",
            "name": _("Campagnes"),
        }


class DoorwayCampaignContactDashboard(models.Model):
    _inherit = "doorway.campaign.contact"

    def _dashboard_row(self):
        self.ensure_one()
        name = " ".join(p for p in (self.first_name, self.last_name) if p).strip()
        return {
            "id": self.id,
            "name": name or "—",
            "phone": self.phone_number or "",
            "last_attempt": fields.Datetime.to_string(self.last_attempt_date)
            if self.last_attempt_date
            else "",
            "duration": self.last_duration or 0,
            "status": self.operational_status,
            "status_label": OP_STATUS_LABELS.get(
                self.operational_status, self.operational_status
            ),
            "ai_note": (self.ai_note or "")[:120],
            "ai_score": self.ai_score or 0,
            "agent_name": self.ia_agent_id.name or "—",
            "has_crm_lead": bool(self.crm_lead_id),
        }

    def _dashboard_drawer_payload(self):
        self.ensure_one()
        Log = self.env["doorway.call.log"]
        Session = self.env["doorway.call.session"]
        phone = (self.phone_number or "").strip()
        attempts = Log.search_read(
            [
                ("campaign_id", "=", self.campaign_id.id),
                ("phone_number", "=", phone),
            ],
            ["call_date", "duration", "amd_result", "disposition", "agent_name"],
            order="call_date desc",
            limit=30,
        )
        session = Session.search(
            [("to_number", "=", phone)],
            order="date_start desc",
            limit=1,
        )
        name = " ".join(p for p in (self.first_name, self.last_name) if p).strip()
        return {
            "id": self.id,
            "name": name or "—",
            "phone": phone,
            "email": self.email or "",
            "pipeline": self.campaign_id.pipeline,
            "operational_status": self.operational_status,
            "status_label": OP_STATUS_LABELS.get(
                self.operational_status, self.operational_status
            ),
            "ai_score": self.ai_score or 0,
            "ai_tags": self.ai_tags or "",
            "ai_note": self.ai_note or "",
            "crm_lead_id": self.crm_lead_id.id or False,
            "attempts": attempts,
            "transcript": session.transcript if session else "",
            "agent_name": self.ia_agent_id.name or "—",
        }

    def dashboard_create_crm_lead(self):
        self.ensure_one()
        if self.crm_lead_id:
            return {"lead_id": self.crm_lead_id.id, "created": False}
        result = self.campaign_id.dashboard_push_crm([self.id])
        return {
            "lead_id": self.crm_lead_id.id,
            "created": bool(result.get("count")),
        }
