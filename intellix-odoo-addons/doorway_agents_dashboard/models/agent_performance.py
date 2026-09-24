# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PIPELINE_LABELS = {
    "renovation": "Rénovation",
    "immobilier": "Immobilier",
    "marketing": "Marketing",
    "driven": "Driven",
    "assurance": "Assurance",
    "doorway": "Doorway",
}

TYPE_LABELS = {
    "inbound": "Inbound",
    "outbound": "Outbound",
    "followup": "Followup",
}

LANG_LABELS = {
    "fr": "Français",
    "en": "Anglais",
    "es": "Español",
    "bilingual": "Multilingue",
}

COST_PER_MINUTE_EUR = 0.22
QUALIFIED_DISPOSITIONS = ("VENTE", "INTERET")
AMD_MACHINE = ("answering_machine", "amd_hangup")


class AgentProfilePerformance(models.Model):
    _inherit = "doorway.agent.profile"

    performance_analysis_at = fields.Datetime(string="Dernière analyse coaching")
    performance_weaknesses_json = fields.Text(string="Faiblesses (JSON)")
    performance_suggestions_json = fields.Text(string="Suggestions prompt (JSON)")

    total_appels = fields.Integer(string="Total appels", compute="_compute_production_kpis")
    appels_7j = fields.Integer(string="Appels 7 jours", compute="_compute_production_kpis")
    appels_30j = fields.Integer(string="Appels 30 jours", compute="_compute_production_kpis")
    taux_decroches = fields.Float(
        string="Taux décroché (%)", compute="_compute_production_kpis", digits=(5, 1)
    )
    taux_repondeurs = fields.Float(
        string="Taux répondeurs (%)", compute="_compute_production_kpis", digits=(5, 1)
    )
    taux_conversion = fields.Float(
        string="Taux conversion (%)",
        compute="_compute_production_kpis",
        digits=(5, 1),
        search="_search_taux_conversion",
    )
    leads_qualifies = fields.Integer(
        string="Leads qualifiés", compute="_compute_production_kpis"
    )
    leads_qualifies_30j = fields.Integer(
        string="Leads qualifiés 30j",
        compute="_compute_production_kpis",
        search="_search_leads_qualifies_30j",
    )
    duree_moy_appel = fields.Float(
        string="Durée moy. appel (sec)", compute="_compute_production_kpis", digits=(6, 1)
    )
    score_ia_moyen = fields.Float(
        string="Score IA moyen",
        compute="_compute_production_kpis",
        digits=(5, 1),
        search="_search_score_ia_moyen",
    )
    cout_total_eur = fields.Float(
        string="Coût total (€)", compute="_compute_production_kpis", digits=(10, 4)
    )
    cout_par_lead = fields.Float(
        string="Coût / lead (€)", compute="_compute_production_kpis", digits=(8, 2)
    )
    nb_campagnes_actives = fields.Integer(
        string="Campagnes actives", compute="_compute_campagnes_actives"
    )

    def _production_call_logs(self):
        self.ensure_one()
        Campaign = self.env.get("doorway.campaign")
        CallLog = self.env.get("doorway.call.log")
        if not Campaign or not CallLog:
            return CallLog or self.env["doorway.call.log"]
        campaigns = Campaign.search([("ia_agent_id", "=", self.id)])
        if not campaigns:
            return CallLog
        return CallLog.search([("campaign_id", "in", campaigns.ids)])

    def _all_call_rows(self):
        """Logs production + sessions pour KPIs globaux."""
        self.ensure_one()
        logs = self._production_call_logs()
        Session = self.env["doorway.call.session"]
        sessions = Session.search([("agent_id", "=", self.id)])
        return logs, sessions

    def _linked_campaigns(self):
        Campaign = self.env.get("doorway.campaign")
        if not Campaign:
            return Campaign
        return Campaign.search([("ia_agent_id", "in", self.ids)])

    @api.depends("status")
    def _compute_campagnes_actives(self):
        Campaign = self.env.get("doorway.campaign")
        for agent in self:
            if not Campaign:
                agent.nb_campagnes_actives = 0
                continue
            agent.nb_campagnes_actives = Campaign.search_count(
                [
                    ("ia_agent_id", "=", agent.id),
                    ("state", "=", "active"),
                ]
            )

    @api.model
    def _search_kpi_numeric(self, field_name, operator, value):
        agents = self.search([("status", "in", ("active", "inactive", "error"))])
        agents._compute_production_kpis()
        matching = []
        for agent in agents:
            field_val = getattr(agent, field_name) or 0
            if operator == ">" and field_val > value:
                matching.append(agent.id)
            elif operator == ">=" and field_val >= value:
                matching.append(agent.id)
            elif operator == "<" and field_val < value:
                matching.append(agent.id)
            elif operator == "<=" and field_val <= value:
                matching.append(agent.id)
            elif operator == "=" and field_val == value:
                matching.append(agent.id)
        return [("id", "in", matching)]

    @api.model
    def _search_leads_qualifies_30j(self, operator, value):
        return self._search_kpi_numeric("leads_qualifies_30j", operator, value)

    @api.model
    def _search_score_ia_moyen(self, operator, value):
        return self._search_kpi_numeric("score_ia_moyen", operator, value)

    @api.model
    def _search_taux_conversion(self, operator, value):
        return self._search_kpi_numeric("taux_conversion", operator, value)

    @api.depends(
        "test_call_ids",
        "test_call_ids.score_global",
        "avg_call_score",
    )
    def _compute_production_kpis(self):
        now = fields.Datetime.now()
        j7 = now - timedelta(days=7)
        j30 = now - timedelta(days=30)
        Report = self.env["doorway.call.report"]

        for agent in self:
            logs, sessions = agent._all_call_rows()
            total = len(logs) + len(sessions)
            logs_7j = logs.filtered(lambda l: l.call_date and l.call_date >= j7)
            sess_7j = sessions.filtered(lambda s: s.date_start and s.date_start >= j7)
            logs_30j = logs.filtered(lambda l: l.call_date and l.call_date >= j30)
            sess_30j = sessions.filtered(lambda s: s.date_start and s.date_start >= j30)

            agent.total_appels = total
            agent.appels_7j = len(logs_7j) + len(sess_7j)
            agent.appels_30j = len(logs_30j) + len(sess_30j)

            humains_logs = logs.filtered(lambda l: l.amd_result == "human")
            repondeurs = logs.filtered(
                lambda l: l.amd_result in AMD_MACHINE
                or l.disposition == "REPONDEUR"
            )
            log_total = len(logs) or 1
            agent.taux_decroches = len(humains_logs) / log_total * 100 if logs else 0
            agent.taux_repondeurs = len(repondeurs) / log_total * 100 if logs else 0

            leads_ok = logs.filtered(
                lambda l: l.disposition in QUALIFIED_DISPOSITIONS
            )
            agent.leads_qualifies = len(leads_ok)
            agent.leads_qualifies_30j = len(
                leads_ok.filtered(lambda l: l.call_date and l.call_date >= j30)
            )
            humain_count = len(humains_logs) or 0
            agent.taux_conversion = (
                len(leads_ok) / humain_count * 100 if humain_count else 0
            )

            durees = [l.duration for l in humains_logs if l.duration]
            for sess in sessions:
                if sess.duration:
                    durees.append(sess.duration)
            agent.duree_moy_appel = sum(durees) / len(durees) if durees else 0
            agent.cout_total_eur = sum(
                (l.duration or 0) * COST_PER_MINUTE_EUR / 60.0 for l in humains_logs
            )
            agent.cout_par_lead = (
                agent.cout_total_eur / agent.leads_qualifies
                if agent.leads_qualifies
                else 0
            )

            scores = list(agent.test_call_ids.filtered(
                lambda c: c.state == "done"
            ).mapped("score_global"))
            reports = Report.search([("agent_id", "=", agent.id)])
            scores.extend([(r.score_global or 0) * 10 for r in reports])
            agent.score_ia_moyen = (
                sum(scores) / len(scores) if scores else (agent.avg_call_score or 0)
            )

    @api.model
    def get_calls_per_day(self, agent_id, nb_jours=30):
        """Appels groupés par jour pour le graphique OWL."""
        agent = self.browse(agent_id).exists()
        if not agent:
            return []
        nb_jours = int(nb_jours or 30)
        now = fields.Datetime.now()
        cutoff = now - timedelta(days=nb_jours)
        logs = agent._production_call_logs().filtered(
            lambda l: l.call_date and l.call_date >= cutoff
        )
        result = []
        for i in range(nb_jours):
            day = (cutoff + timedelta(days=i)).date()
            day_start = fields.Datetime.start_of(day, "day")
            day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
            day_logs = logs.filtered(
                lambda l, ds=day_start, de=day_end: l.call_date
                and ds <= l.call_date <= de
            )
            result.append(
                {
                    "date": day.strftime("%d/%m"),
                    "humains": len(
                        day_logs.filtered(lambda l: l.amd_result == "human")
                    ),
                    "repondeurs": len(
                        day_logs.filtered(
                            lambda l: l.amd_result in AMD_MACHINE
                            or l.disposition == "REPONDEUR"
                        )
                    ),
                    "leads": len(
                        day_logs.filtered(
                            lambda l: l.disposition in QUALIFIED_DISPOSITIONS
                        )
                    ),
                }
            )
        return result

    def action_view_performance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "performance_dashboard_action",
            "name": _("Performance — %s") % self.name,
            "context": {"default_agent_id": self.id},
        }

    def action_view_calls(self):
        self.ensure_one()
        Campaign = self.env.get("doorway.campaign")
        campaigns = (
            Campaign.search([("ia_agent_id", "=", self.id)]) if Campaign else []
        )
        CallLog = self.env.get("doorway.call.log")
        if not CallLog:
            raise UserError(_("Module Appels non disponible."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Appels — %s") % self.name,
            "res_model": "doorway.call.log",
            "view_mode": "list,form",
            "domain": [("campaign_id", "in", campaigns.ids)],
            "context": {"default_campaign_id": campaigns[:1].id if campaigns else False},
        }

    def _period_start(self, days):
        return fields.Datetime.now() - timedelta(days=int(days or 7))

    def _score_trend(self, days=7):
        self.ensure_one()
        now = fields.Datetime.now()
        cur_start = now - timedelta(days=days)
        prev_start = now - timedelta(days=days * 2)
        TestCall = self.env["doorway.agent.test.call"]
        cur = TestCall.search(
            [
                ("agent_id", "=", self.id),
                ("state", "=", "done"),
                ("create_date", ">=", cur_start),
            ]
        )
        prev = TestCall.search(
            [
                ("agent_id", "=", self.id),
                ("state", "=", "done"),
                ("create_date", ">=", prev_start),
                ("create_date", "<", cur_start),
            ]
        )
        cur_avg = sum(cur.mapped("score_global")) / len(cur) if cur else 0
        prev_avg = sum(prev.mapped("score_global")) / len(prev) if prev else 0
        if not cur and not prev:
            return "stable", 0.0
        if cur_avg > prev_avg + 2:
            return "up", cur_avg - prev_avg
        if cur_avg < prev_avg - 2:
            return "down", prev_avg - cur_avg
        return "stable", 0.0

    @api.model
    def performance_list_agents(self, filters=None):
        filters = filters or {}
        domain = [("status", "in", ("active", "inactive"))]
        if filters.get("pipeline"):
            domain.append(("pipeline", "=", filters["pipeline"]))
        if filters.get("agent_type"):
            domain.append(("agent_type", "=", filters["agent_type"]))
        if filters.get("language"):
            domain.append(("language", "=", filters["language"]))
        if filters.get("status"):
            domain.append(("status", "=", filters["status"]))
        Campaign = self.env.get("doorway.campaign")
        if filters.get("campaign_id") and Campaign:
            camp = Campaign.browse(int(filters["campaign_id"])).exists()
            if camp and camp.ia_agent_id:
                domain.append(("id", "=", camp.ia_agent_id.id))

        agents = self.search(domain, order="name")
        campaigns = (
            Campaign.search([("ia_agent_id", "!=", False)], order="name")
            if Campaign
            else []
        )
        rows = []
        for agent in agents:
            trend, delta = agent._score_trend(filters.get("period_days", 7))
            score = agent.score_ia_moyen or agent.avg_call_score or 0
            rows.append(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "pipeline": agent.pipeline,
                    "pipeline_label": PIPELINE_LABELS.get(
                        agent.pipeline, agent.pipeline
                    ),
                    "agent_type": agent.agent_type,
                    "agent_type_label": TYPE_LABELS.get(
                        agent.agent_type, agent.agent_type
                    ),
                    "language": agent.language,
                    "language_label": LANG_LABELS.get(
                        agent.language, agent.language
                    ),
                    "score": round(score, 1),
                    "trend": trend,
                    "trend_delta": round(delta, 1),
                    "total_calls": agent.total_appels or agent.total_test_calls,
                    "appels_7j": agent.appels_7j,
                    "taux_decroches": round(agent.taux_decroches, 1),
                    "taux_conversion": round(agent.taux_conversion, 1),
                    "leads_qualifies_30j": agent.leads_qualifies_30j,
                    "cout_par_lead": round(agent.cout_par_lead, 2),
                    "nb_campagnes_actives": agent.nb_campagnes_actives,
                    "status": agent.status,
                }
            )
        return {
            "agents": rows,
            "pipelines": [
                {"value": k, "label": v} for k, v in PIPELINE_LABELS.items()
            ],
            "campaigns": [
                {"id": c.id, "name": c.name, "vicidial_id": c.vicidial_campaign_id}
                for c in campaigns
            ],
            "languages": [
                {"value": k, "label": v} for k, v in LANG_LABELS.items()
            ],
        }

    def performance_agent_detail(self, period_days=30, call_page=1, page_size=20):
        self.ensure_one()
        since = self._period_start(period_days)
        calls, total = self._performance_collect_calls(
            since, page=int(call_page), page_size=int(page_size)
        )
        metrics = self._performance_aggregate_metrics(since)
        satisfaction = self._performance_satisfaction(since, metrics)
        analysis = self._performance_cached_analysis()
        feedbacks = self.env["doorway.agent.feedback"].list_for_agent(self.id, limit=15)
        user_csat = self._performance_user_csat(since)
        return {
            "agent": {
                "id": self.id,
                "name": self.name,
                "pipeline": self.pipeline,
                "pipeline_label": PIPELINE_LABELS.get(
                    self.pipeline, self.pipeline
                ),
                "agent_type": self.agent_type,
                "system_prompt": self.system_prompt or "",
                "score": round(
                    self.score_ia_moyen
                    or self.avg_call_score
                    or self.last_test_score
                    or 0,
                    1,
                ),
            },
            "production_kpis": {
                "total_appels": self.total_appels,
                "appels_30j": self.appels_30j,
                "taux_decroches": round(self.taux_decroches, 1),
                "taux_repondeurs": round(self.taux_repondeurs, 1),
                "taux_conversion": round(self.taux_conversion, 1),
                "leads_qualifies": self.leads_qualifies,
                "leads_qualifies_30j": self.leads_qualifies_30j,
                "duree_moy_appel": round(self.duree_moy_appel, 1),
                "cout_total_eur": round(self.cout_total_eur, 4),
                "cout_par_lead": round(self.cout_par_lead, 2),
                "nb_campagnes_actives": self.nb_campagnes_actives,
            },
            "calls_per_day": self.get_calls_per_day(self.id, period_days),
            "metrics": metrics,
            "satisfaction": satisfaction,
            "calls": calls,
            "pagination": {
                "page": int(call_page),
                "page_size": int(page_size),
                "total": total,
                "pages": max(1, (total + int(page_size) - 1) // int(page_size)),
            },
            "weaknesses": analysis.get("weaknesses", []),
            "prompt_suggestions": analysis.get("prompt_suggestions", []),
            "analysis_at": fields.Datetime.to_string(self.performance_analysis_at)
            if self.performance_analysis_at
            else "",
            "feedbacks": feedbacks,
            "user_csat": user_csat,
        }

    def _performance_user_csat(self, since):
        Feedback = self.env["doorway.agent.feedback"]
        rows = Feedback.search(
            [
                ("agent_id", "=", self.id),
                ("create_date", ">=", since),
            ]
        )
        if not rows:
            return {"avg": 0, "count": 0}
        ratings = [int(r.rating) for r in rows if r.rating]
        return {
            "avg": round(sum(ratings) / len(ratings), 1) if ratings else 0,
            "count": len(rows),
        }

    def _performance_collect_calls(self, since, page=1, page_size=20):
        TestCall = self.env["doorway.agent.test.call"]
        Session = self.env["doorway.call.session"]
        Report = self.env["doorway.call.report"]

        test_calls = TestCall.search(
            [
                ("agent_id", "=", self.id),
                ("state", "=", "done"),
                ("create_date", ">=", since),
            ],
            order="create_date desc",
        )
        sessions = Session.search(
            [
                ("agent_id", "=", self.id),
                ("date_start", ">=", since),
            ],
            order="date_start desc",
        )
        rows = []
        for tc in test_calls:
            rows.append(
                {
                    "id": "tc-%s" % tc.id,
                    "source": "test",
                    "date": fields.Datetime.to_string(tc.create_date),
                    "duration": tc.duration_seconds or 0,
                    "status": "done",
                    "score": tc.score_global or 0,
                    "sentiment": self._sentiment_from_score(tc.score_global),
                    "tags": self._tags_from_test_call(tc),
                    "transcript": tc.transcript or "",
                    "note": (tc.analyse_ia or "")[:200],
                }
            )
        for sess in sessions:
            report = Report.search([("session_id", "=", sess.id)], limit=1)
            score = (report.score_global * 10) if report else 0
            rows.append(
                {
                    "id": "cs-%s" % sess.id,
                    "source": "session",
                    "date": fields.Datetime.to_string(sess.date_start),
                    "duration": sess.duration or 0,
                    "status": sess.call_status,
                    "score": score,
                    "sentiment": self._sentiment_from_score(score),
                    "tags": self._tags_from_report(report),
                    "transcript": sess.transcript or "",
                    "note": (report.claude_summary if report else "")[:200],
                }
            )
        rows.sort(key=lambda r: r.get("date") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    @staticmethod
    def _sentiment_from_score(score):
        if score >= 70:
            return "positif"
        if score >= 40:
            return "neutre"
        return "négatif"

    @staticmethod
    def _tags_from_test_call(tc):
        tags = []
        if tc.faiblesses and "prix" in (tc.faiblesses or "").lower():
            tags.append("objection-prix")
        if tc.score_conversion and tc.score_conversion >= 15:
            tags.append("très-intéressé")
        if tc.recommandations and "rappel" in (tc.recommandations or "").lower():
            tags.append("rappel-demandé")
        if tc.score_global and tc.score_global >= 75:
            tags.append("succès")
        return tags or ["analysé"]

    @staticmethod
    def _tags_from_report(report):
        if not report:
            return []
        tags = []
        if report.prochaine_action == "rappel":
            tags.append("rappel-demandé")
        if report.score_global and report.score_global >= 8:
            tags.append("succès")
        if report.points_amelioration and "prix" in (
            report.points_amelioration or ""
        ).lower():
            tags.append("objection-prix")
        return tags or ["analysé"]

    def _performance_aggregate_metrics(self, since):
        self.ensure_one()
        TestCall = self.env["doorway.agent.test.call"]
        Report = self.env["doorway.call.report"]
        tests = TestCall.search(
            [
                ("agent_id", "=", self.id),
                ("state", "=", "done"),
                ("create_date", ">=", since),
            ]
        )
        reports = Report.search(
            [
                ("agent_id", "=", self.id),
                ("create_date", ">=", since),
            ]
        )

        def avg(vals):
            vals = [v for v in vals if v]
            return round(sum(vals) / len(vals), 1) if vals else 0.0

        clarte = []
        objections = []
        qualification = []
        script = []
        conversion = []
        for tc in tests:
            clarte.append(tc.score_fluidite)
            objections.append(tc.score_pertinence)
            qualification.append(tc.score_conversion)
            script.append(tc.score_pertinence)
            conversion.append(tc.score_conversion)
        for rep in reports:
            clarte.append((rep.score_accroche or 0) * 2)
            objections.append((rep.score_objections or 0) * 2)
            qualification.append((rep.score_qualification or 0) * 2)
            script.append((rep.score_accroche or 0) * 2)
            conversion.append((rep.score_closing or 0) * 2)

        return {
            "clarte": avg(clarte),
            "objections": avg(objections),
            "qualification": avg(qualification),
            "script": avg(script),
            "conversion": avg(conversion),
        }

    def _performance_satisfaction(self, since, metrics):
        self.ensure_one()
        TestCall = self.env["doorway.agent.test.call"]
        Session = self.env["doorway.call.session"]
        tests = TestCall.search(
            [
                ("agent_id", "=", self.id),
                ("state", "=", "done"),
                ("create_date", ">=", since),
            ]
        )
        sessions = Session.search(
            [
                ("agent_id", "=", self.id),
                ("date_start", ">=", since),
            ]
        )
        durations = []
        early_hangup = 0
        sentiments = {"positif": 0, "neutre": 0, "négatif": 0}
        for tc in tests:
            d = tc.duration_seconds or 0
            durations.append(d)
            if 0 < d < 30:
                early_hangup += 1
            s = self._sentiment_from_score(tc.score_global)
            sentiments[s] = sentiments.get(s, 0) + 1
        for sess in sessions:
            d = sess.duration or 0
            durations.append(d)
            if 0 < d < 30:
                early_hangup += 1
        total_calls = len(tests) + len(sessions)
        avg_duration = round(sum(durations) / len(durations), 0) if durations else 0
        hangup_rate = round(
            (early_hangup / total_calls * 100) if total_calls else 0, 1
        )
        global_score = self.avg_call_score or self.last_test_score or 0
        csat = round(min(5.0, (global_score / 100) * 5), 1)
        return {
            "csat": csat,
            "sentiments": sentiments,
            "avg_duration_sec": int(avg_duration),
            "early_hangup_rate": hangup_rate,
        }

    def _performance_cached_analysis(self):
        self.ensure_one()
        try:
            weaknesses = json.loads(self.performance_weaknesses_json or "[]")
        except json.JSONDecodeError:
            weaknesses = []
        try:
            suggestions = json.loads(self.performance_suggestions_json or "[]")
        except json.JSONDecodeError:
            suggestions = []
        return {
            "weaknesses": weaknesses,
            "prompt_suggestions": suggestions,
        }

    def performance_run_analysis(self, limit=30):
        """Analyse Claude sur transcriptions + retours utilisateurs."""
        self.ensure_one()
        since = self._period_start(30)
        calls, _total = self._performance_collect_calls(since, page=1, page_size=limit)
        transcriptions = [
            {"date": c["date"], "text": c.get("transcript") or ""}
            for c in calls
            if c.get("transcript")
        ]
        feedbacks = self.env["doorway.agent.feedback"].search(
            [("agent_id", "=", self.id), ("create_date", ">=", since)],
            order="create_date desc",
            limit=20,
        )
        for fb in feedbacks:
            if fb.comment:
                transcriptions.insert(
                    0,
                    {
                        "date": fields.Datetime.to_string(fb.create_date),
                        "text": (
                            "[RETOUR UTILISATEUR %s/5] %s"
                            % (fb.rating, fb.comment)
                        ),
                    },
                )
        if not transcriptions:
            raise UserError(
                _("Aucune transcription ni retour utilisateur sur les 30 derniers jours.")
            )

        from odoo.addons.doorway_agents_dashboard.services.claude_service import (
            ClaudeService,
        )

        result = ClaudeService(self.env).analyze_agent_coaching(
            transcriptions,
            self.system_prompt or "",
        )
        self.write(
            {
                "performance_analysis_at": fields.Datetime.now(),
                "performance_weaknesses_json": json.dumps(
                    result.get("weaknesses") or [], ensure_ascii=False
                ),
                "performance_suggestions_json": json.dumps(
                    result.get("prompt_suggestions") or [], ensure_ascii=False
                ),
            }
        )
        return result

    def performance_apply_suggestions(self, suggestions=None):
        """Intègre les suggestions au prompt et ouvre le wizard étape 4."""
        self.ensure_one()
        if suggestions is None:
            cached = self._performance_cached_analysis()
            suggestions = cached.get("prompt_suggestions") or []
        if isinstance(suggestions, str):
            suggestions = [suggestions]
        block = "\n".join("- %s" % s for s in suggestions if s)
        prompt = (self.system_prompt or "").strip()
        if not prompt:
            prompt = self.get_effective_prompt_info().get("prompt") or ""
        marker = self.IMPROVEMENTS_MARKER
        if marker in prompt:
            prompt = prompt.split(marker, 1)[0].rstrip()
        if block:
            prompt = (
                prompt.rstrip()
                + "\n\n%s (Claude)\n" % marker
                + block
                + "\n"
            )
        self.write({"system_prompt": prompt, "wizard_step": "prompt"})
        if self.materialize_compiled_prompt():
            try:
                self.sync_prompt_to_elevenlabs()
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Sync EL après materialize %s: %s", self.id, exc)
        return {
            "type": "ir.actions.client",
            "tag": "agent_wizard_action",
            "name": _("Modifier le prompt"),
            "context": {
                "default_agent_id": self.id,
                "open_wizard_step": "prompt",
            },
        }

    @api.model
    def performance_analyze_api(self, agent_id, transcriptions=None, current_prompt=None):
        """Point d'entrée API /api/intellix/agent/analyze."""
        agent = self.browse(agent_id).exists()
        if not agent:
            return {"status": "error", "message": "Agent introuvable."}
        if not transcriptions:
            result = agent.performance_run_analysis()
        else:
            from odoo.addons.doorway_agents_dashboard.services.claude_service import (
                ClaudeService,
            )

            result = ClaudeService(self.env).analyze_agent_coaching(
                transcriptions,
                current_prompt or agent.system_prompt or "",
            )
            agent.write(
                {
                    "performance_analysis_at": fields.Datetime.now(),
                    "performance_weaknesses_json": json.dumps(
                        result.get("weaknesses") or [], ensure_ascii=False
                    ),
                    "performance_suggestions_json": json.dumps(
                        result.get("prompt_suggestions") or [], ensure_ascii=False
                    ),
                }
            )
        return {
            "status": "ok",
            "weaknesses": result.get("weaknesses") or [],
            "prompt_suggestions": result.get("prompt_suggestions") or [],
        }
