# -*- coding: utf-8 -*-
"""Collecte de données cross-modules pour People Engine."""
from datetime import date, datetime, timedelta


class PeopleEngineCollector:
    """Service stateless — passer profile.env via profile."""

    def collect_all(self, profile, period_start=None, period_end=None):
        period_end = period_end or date.today()
        period_start = period_start or (period_end - timedelta(days=30))
        metrics = {}
        metrics.update(self._collect_crm(profile, period_start, period_end))
        metrics.update(self._collect_project(profile, period_start, period_end))
        metrics.update(self._collect_agents_ia(profile, period_start, period_end))
        metrics.update(self._collect_activity(profile, period_start, period_end))
        return metrics

    def apply_to_profile(self, profile, metrics, period_start, period_end):
        """Écrit les métriques collectées sur le profil."""
        profile.write(
            {
                "metric_period_start": period_start,
                "metric_period_end": period_end,
                "crm_leads_assigned": metrics.get("crm_leads_total", 0),
                "crm_leads_won": metrics.get("crm_leads_won", 0),
                "crm_conversion_rate": metrics.get("crm_conversion_rate", 0.0),
                "crm_avg_response_time": metrics.get("crm_avg_response_time", 0.0),
                "crm_revenue_generated": metrics.get("crm_revenue", 0.0),
                "project_tasks_assigned": metrics.get("project_tasks_total", 0),
                "project_tasks_done": metrics.get("project_tasks_done", 0),
                "project_tasks_ontime": metrics.get("project_tasks_ontime", 0),
                "project_ontime_rate": metrics.get("project_ontime_rate", 0.0),
                "project_avg_completion_days": metrics.get(
                    "project_avg_completion_days", 0.0
                ),
                "ia_calls_made": metrics.get("ia_calls_total", 0),
                "ia_avg_quality_score": metrics.get("ia_avg_quality", 0.0),
                "ia_avg_call_duration": metrics.get("ia_avg_duration", 0.0),
                "ia_conversion_rate": metrics.get("ia_conversion_rate", 0.0),
                "activity_login_days": metrics.get("activity_login_days", 0),
                "activity_messages_sent": metrics.get("activity_messages", 0),
                "activity_tasks_created": metrics.get("activity_completed", 0),
            }
        )

    def _period_datetimes(self, start, end):
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        return start_dt, end_dt

    def _collect_crm(self, profile, start, end):
        try:
            env = profile.env
            user = profile.user_id
            if not user:
                return {}
            start_dt, end_dt = self._period_datetimes(start, end)
            leads = env["crm.lead"].search(
                [
                    ("user_id", "=", user.id),
                    ("create_date", ">=", start_dt),
                    ("create_date", "<=", end_dt),
                ]
            )
            won = leads.filtered(
                lambda l: l.probability >= 100
                or (l.stage_id and l.stage_id.is_won)
            )
            lost = leads.filtered(lambda l: not l.active)
            revenues = won.mapped("expected_revenue")
            return {
                "crm_leads_total": len(leads),
                "crm_leads_won": len(won),
                "crm_leads_lost": len(lost),
                "crm_conversion_rate": round(len(won) / len(leads) * 100, 1) if leads else 0,
                "crm_revenue": sum(revenues),
                "crm_avg_deal_size": sum(revenues) / len(won) if won else 0,
                "crm_avg_response_time": 0.0,
            }
        except Exception as exc:  # noqa: BLE001
            return {"crm_error": str(exc)}

    def _collect_project(self, profile, start, end):
        try:
            env = profile.env
            user = profile.user_id
            if not user:
                return {}
            start_dt, end_dt = self._period_datetimes(start, end)
            tasks = env["project.task"].search(
                [
                    ("user_ids", "in", user.id),
                    ("create_date", ">=", start_dt),
                    ("create_date", "<=", end_dt),
                ]
            )
            done = tasks.filtered(lambda t: t.is_closed)
            overdue = tasks.filtered(
                lambda t: t.date_deadline
                and not t.is_closed
                and t.date_deadline < date.today()
            )
            ontime = done.filtered(
                lambda t: t.date_deadline
                and t.write_date
                and t.write_date.date() <= t.date_deadline
            )
            completion_days = []
            for task in done:
                if task.create_date and task.write_date:
                    completion_days.append(
                        (task.write_date - task.create_date).days
                    )
            return {
                "project_tasks_total": len(tasks),
                "project_tasks_done": len(done),
                "project_tasks_overdue": len(overdue),
                "project_tasks_ontime": len(ontime),
                "project_ontime_rate": round(len(ontime) / len(done) * 100, 1)
                if done
                else 0,
                "project_avg_completion_days": (
                    sum(completion_days) / len(completion_days) if completion_days else 0
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {"project_error": str(exc)}

    def _collect_agents_ia(self, profile, start, end):
        try:
            env = profile.env
            if "doorway.call.session" not in env:
                return {}
            user = profile.user_id
            if not user:
                return {}
            start_dt, end_dt = self._period_datetimes(start, end)
            sessions = env["doorway.call.session"].search(
                [
                    ("call_status", "=", "completed"),
                    ("date_start", ">=", start_dt),
                    ("date_start", "<=", end_dt),
                ]
            )
            user_sessions = sessions.filtered(
                lambda s: s.lead_id and s.lead_id.user_id.id == user.id
            )
            scores = []
            durations = []
            for session in user_sessions:
                if session.report_id and session.report_id.score_global:
                    scores.append(session.report_id.score_global)
                if session.duration:
                    durations.append(session.duration)
            won_leads = user_sessions.filtered(
                lambda s: s.lead_id
                and (s.lead_id.probability >= 100 or s.lead_id.stage_id.is_won)
            )
            return {
                "ia_calls_total": len(user_sessions),
                "ia_avg_quality": sum(scores) / len(scores) if scores else 0,
                "ia_avg_duration": sum(durations) / len(durations) if durations else 0,
                "ia_conversion_rate": round(len(won_leads) / len(user_sessions) * 100, 1)
                if user_sessions
                else 0,
            }
        except Exception:  # noqa: BLE001
            return {}

    def _collect_activity(self, profile, start, end):
        try:
            env = profile.env
            user = profile.user_id
            if not user:
                return {}
            start_dt, end_dt = self._period_datetimes(start, end)
            partner = user.partner_id
            messages = 0
            if partner:
                messages = env["mail.message"].search_count(
                    [
                        ("author_id", "=", partner.id),
                        ("date", ">=", start_dt),
                        ("date", "<=", end_dt),
                        ("message_type", "in", ["comment", "email", "comment"]),
                    ]
                )
            activities_done = env["mail.activity"].search_count(
                [
                    ("user_id", "=", user.id),
                    ("active", "=", False),
                    ("date_done", ">=", start),
                    ("date_done", "<=", end),
                ]
            )
            logins = env["res.users.log"].search_count(
                [
                    ("create_uid", "=", user.id),
                    ("create_date", ">=", start_dt),
                    ("create_date", "<=", end_dt),
                ]
            ) if "res.users.log" in env else 0
            return {
                "activity_messages": messages,
                "activity_completed": activities_done,
                "activity_login_days": logins,
            }
        except Exception as exc:  # noqa: BLE001
            return {"activity_error": str(exc)}
