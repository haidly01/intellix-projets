# -*- coding: utf-8 -*-
import datetime
from odoo import api, fields, models

class VicidialSupervisorDashboard(models.Model):
    _inherit = "doorway.vicidial.agent.session"

    @api.model
    def _selection_labels(self, field):
        if not field or not field.selection:
            return {}
        selection = field.selection
        if callable(selection):
            selection = selection(self.env[self._name])
        return dict(selection)

    @api.model
    def _supervisor_date_range(self, date_from=None, date_to=None):
        today = fields.Date.today()
        if not date_from:
            date_from = fields.Date.to_string(today)
        if not date_to:
            date_to = fields.Date.to_string(today)
        start_dt = datetime.datetime.combine(fields.Date.from_string(date_from), datetime.time.min)
        end_dt = datetime.datetime.combine(fields.Date.from_string(date_to), datetime.time.max)
        return date_from, date_to, start_dt, end_dt

    @api.model
    def get_supervisor_dashboard_data(
        self,
        date_from=None,
        date_to=None,
        campaign_vicidial_id=None,
        campaign_state=None,
    ):
        date_from, date_to, start_dt, end_dt = self._supervisor_date_range(date_from, date_to)
        Campaign = self.env["doorway.campaign"].sudo()
        Agent = self.env["doorway.campaign.agent.user"].sudo()
        Session = self.sudo()
        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        Lead = self.env["crm.lead"].sudo()
        campaigns_raw = Campaign.action_get_monitor_dashboard()
        campaign_state_labels = dict(Campaign._fields["state"].selection)
        campaigns, live_agents, calls_live = [], 0, 0
        amd_human = amd_machine = active_campaigns = 0
        for row in campaigns_raw:
            live = row.get("live_stats") or {}
            live_agents += live.get("live_agents") or 0
            calls_live += live.get("total_calls") or row.get("total_called") or 0
            amd_human += live.get("amd_human") or 0
            amd_machine += live.get("amd_machine") or 0
            if row.get("is_dialing_prod") or row.get("dial_site") == "hostinger":
                active_campaigns += 1
            campaigns.append({
                **row,
                "state_label": campaign_state_labels.get(row.get("state"), row.get("state")),
                "operational_label": row.get("operational_label") or "",
                "dial_site": row.get("dial_site") or "",
                "is_dialing_prod": bool(row.get("is_dialing_prod")),
                "live_agents": live.get("live_agents") or 0,
                "calls_today": live.get("total_calls") or row.get("total_called") or 0,
            })
        coaching_data = Lead.get_calls_coaching_dashboard(
            date_from=date_from,
            date_to=date_to,
            qualifications=["all"],
            campaign_vicidial_id=campaign_vicidial_id,
            campaign_state=campaign_state,
        )
        qual_kpis = coaching_data.get("kpis") or {}
        Coaching = self.env.get("pe.coaching.call")
        coaching_stats = {"analysed": 0, "avg_score": 0, "unread": 0}
        if Coaching:
            calls = Coaching.sudo().search([("date_appel", ">=", date_from), ("date_appel", "<=", date_to + " 23:59:59")])
            scores = [c.score_global for c in calls if c.score_global]
            coaching_stats = {"analysed": len(calls.filtered("analyse_done")),
                "avg_score": round(sum(scores) / len(scores)) if scores else 0,
                "unread": len(calls.filtered(lambda c: not c.lu_par_employe and c.visible_employe))}
        active_sessions = Session.search([("state", "in", ("active", "paused"))], order="date_start desc")
        agents_today = []
        for agent in Agent.search([("active", "=", True), ("vicidial_qualification_active", "=", True)], order="full_name, vicidial_user"):
            user = agent.user_id
            if not user:
                continue
            sessions = Session.search([("user_id", "=", user.id), ("date_start", ">=", start_dt), ("date_start", "<=", end_dt)])
            sync_count = Sync.search_count([("user_id", "=", user.id), ("date_debut", ">=", start_dt), ("date_debut", "<=", end_dt)])
            qual_count = Lead.search_count([("user_id", "=", user.id), ("qualification_statut", "!=", False), ("write_date", ">=", start_dt), ("write_date", "<=", end_dt)])
            current = active_sessions.filtered(lambda s: s.user_id == user)[:1]
            agents_today.append({"id": agent.id, "name": agent.full_name or user.name, "vicidial_user": agent.vicidial_user,
                "sessions": len(sessions), "appels": sync_count, "qualifies": sum(sessions.mapped("nb_qualifies")) or qual_count,
                "duree_secondes": sum(sessions.mapped("duree_travail_secondes")), "session_state": current.state if current else False,
                "campaign_name": current.campaign_id.name if current else ""})
        qual_labels = self._selection_labels(Lead._fields.get("qualification_statut"))
        recent_rows = (coaching_data.get("rows") or [])[:25]
        for row in recent_rows:
            if not row.get("qualification_label"):
                row["qualification_label"] = qual_labels.get(row.get("qualification"), row.get("qualification"))
        pending_callbacks = self.env["mail.activity"].sudo().search_count([
            ("res_model", "=", "crm.lead"),
            ("date_deadline", "<=", fields.Date.to_string(fields.Date.today() + datetime.timedelta(days=7))),
            ("date_deadline", ">=", fields.Date.today())])
        if campaign_vicidial_id and campaign_vicidial_id not in ("all", ""):
            campaigns = [c for c in campaigns if c.get("vicidial_campaign_id") == campaign_vicidial_id]
        if campaign_state and campaign_state not in ("all", ""):
            campaigns = [c for c in campaigns if c.get("state") == campaign_state]
        return {"date_from": date_from, "date_to": date_to,
            "refreshed_at": fields.Datetime.to_string(fields.Datetime.now()),
            "campaign_options": Lead.get_dashboard_campaign_options(),
            "campaign_states": coaching_data.get("campaign_states") or [],
            "kpis": {"active_campaigns": active_campaigns, "live_agents": live_agents,
                "calls_period": qual_kpis.get("total") or calls_live, "qualifies": qual_kpis.get("qualifie") or 0,
                "rdv": qual_kpis.get("rdv") or 0, "rappels": qual_kpis.get("a_rappeler") or 0,
                "coaching_avg": coaching_stats["avg_score"], "coaching_analysed": coaching_stats["analysed"],
                "coaching_unread": coaching_stats["unread"], "active_sessions": len(active_sessions),
                "pending_callbacks": pending_callbacks, "amd_human": amd_human, "amd_machine": amd_machine},
            "campaigns": campaigns, "agents": agents_today, "qualification_kpis": qual_kpis, "recent_calls": recent_rows,
            "active_sessions": [{"id": s.id, "agent": s.user_id.name, "vicidial_user": s.vicidial_user or "",
                "campaign": s.campaign_id.name if s.campaign_id else "", "state": s.state, "nb_appels": s.nb_appels,
                "nb_qualifies": s.nb_qualifies, "duree_secondes": s.duree_travail_secondes,
                "since": fields.Datetime.to_string(s.date_start) if s.date_start else ""} for s in active_sessions]}
