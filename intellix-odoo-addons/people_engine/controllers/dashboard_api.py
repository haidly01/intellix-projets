# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PeopleEngineDashboardApi(http.Controller):

    @http.route("/people_engine/api/profile", type="json", auth="user")
    def get_my_profile(self):
        """Données dashboard employé (profil courant)."""
        employee = request.env["hr.employee"].pe_resolve_user_employee()
        if not employee:
            return {"error": "no_employee"}
        profile = request.env["pe.employee.profile"].search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if not profile:
            return {"error": "no_profile"}
        scores = request.env["pe.performance.score"].search_read(
            [("profile_id", "=", profile.id)],
            ["score_global", "period_end", "trend"],
            order="period_end desc",
            limit=6,
        )
        return {
            "profile_id": profile.id,
            "employee": employee.name,
            "score_global": profile.score_global,
            "score_performance": profile.score_performance,
            "score_engagement": profile.score_engagement,
            "score_growth": profile.score_growth,
            "score_trend": profile.score_trend,
            "crm": {
                "leads": profile.crm_leads_assigned,
                "won": profile.crm_leads_won,
                "conversion": profile.crm_conversion_rate,
                "revenue": profile.crm_revenue_generated,
            },
            "project": {
                "tasks": profile.project_tasks_assigned,
                "ontime_rate": profile.project_ontime_rate,
            },
            "ia": {
                "calls": profile.ia_calls_made,
                "quality": profile.ia_avg_quality_score,
            },
            "history": list(reversed(scores)),
            "objectives": profile.objective_ids.read(
                ["name", "achievement_rate", "status", "target_value", "current_value"]
            ),
        }

    @http.route("/people_engine/api/team", type="json", auth="user")
    def get_team_dashboard(self):
        """Vue équipe pour gestionnaire."""
        employee = request.env["hr.employee"].pe_resolve_user_employee()
        if not employee:
            return {"error": "no_employee"}
        domain = [("employee_id.parent_id", "=", employee.id)]
        if request.env.user.has_group("people_engine.group_hr"):
            domain = []
        elif request.env.user.has_group("people_engine.group_manager"):
            domain = [
                "|",
                ("employee_id.parent_id", "=", employee.id),
                ("employee_id", "=", employee.id),
            ]
        else:
            domain = [("employee_id.user_id", "=", request.env.uid)]
        profiles = request.env["pe.employee.profile"].search(domain)
        return {
            "members": [
                {
                    "id": p.id,
                    "name": p.employee_id.name,
                    "score": p.score_global,
                    "trend": p.score_trend,
                    "band": p.performance_band,
                    "alerts": p.alert_count,
                    "status": p.pe_status,
                    "objectives_achieved": len(
                        p.objective_ids.filtered(lambda o: o.status == "achieved")
                    ),
                }
                for p in profiles
            ]
        }

    @http.route("/people_engine/api/hr/kpis", type="json", auth="user")
    def get_hr_kpis(self):
        if not request.env.user.has_group("people_engine.group_hr"):
            return {"error": "access_denied"}
        profiles = request.env["pe.employee.profile"].search([])
        evaluations_pending = request.env["pe.evaluation"].search_count(
            [("status", "in", ["pending_review", "pending_approval"])]
        )
        return {
            "avg_score": sum(profiles.mapped("score_global")) / len(profiles)
            if profiles
            else 0,
            "alert_count": len(profiles.filtered(lambda p: p.score_global < 60)),
            "evaluations_pending": evaluations_pending,
            "employee_count": len(profiles),
        }
