# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEngineTVDashboardService(models.AbstractModel):
    _name = "pe.tv.dashboard.service"
    _description = "Données dashboard TV (publiques uniquement)"

    @api.model
    def _profile_domain(self, department_id):
        domain = [("pe_status", "!=", "inactive")]
        if department_id:
            domain.append(("employee_id.department_id", "=", department_id))
        return domain

    @api.model
    def get_team_score(self, department_id):
        profiles = self.env["pe.employee.profile"].search(
            self._profile_domain(department_id)
        )
        if not profiles:
            return {"avg_score": 0, "count": 0}
        return {
            "avg_score": sum(profiles.mapped("score_global")) / len(profiles),
            "count": len(profiles),
        }

    @api.model
    def get_leaderboard(self, department_id, limit=5):
        profiles = self.env["pe.employee.profile"].search(
            self._profile_domain(department_id),
            order="score_global desc",
            limit=limit,
        )
        return [
            {
                "name": self._public_name(p),
                "score": round(p.score_global, 1),
            }
            for p in profiles
        ]

    @api.model
    def _public_name(self, profile):
        name = profile.employee_id.name or "?"
        parts = name.split()
        if len(parts) > 1:
            return "%s %s." % (parts[0], parts[-1][0])
        return parts[0] if parts else "?"

    @api.model
    def get_recent_badges(self, department_id, limit=8):
        domain = [
            ("manager_approved", "=", True),
            ("is_public", "=", True),
        ]
        if department_id:
            domain.append(
                ("profile_id.employee_id.department_id", "=", department_id)
            )
        awards = self.env["pe.badge.award"].search(
            domain, order="award_date desc", limit=limit
        )
        return [
            {
                "icon": a.badge_id.icon or "🏆",
                "employee_name": self._public_name(a.profile_id),
                "badge_name": a.badge_id.name,
            }
            for a in awards
        ]

    @api.model
    def get_active_challenges(self, department_id):
        challenges = self.env["pe.challenge"].search([("status", "=", "active")])
        result = []
        for ch in challenges:
            if department_id and ch.department_ids and department_id not in ch.department_ids.ids:
                continue
            result.append(
                {
                    "name": ch.name,
                    "metric": ch.metric,
                    "target": ch.target_value,
                    "end": str(ch.date_end) if ch.date_end else "",
                }
            )
        return result

    @api.model
    def get_recent_completions(self, department_id, limit=5):
        domain = [("status", "=", "completed")]
        if department_id:
            domain.append(
                ("profile_id.employee_id.department_id", "=", department_id)
            )
        enrollments = self.env["pe.enrollment"].search(
            domain, order="date_completed desc", limit=limit
        )
        return [
            {
                "employee_name": self._public_name(e.profile_id),
                "course_title": e.course_id.title,
            }
            for e in enrollments
        ]

    @api.model
    def get_tv_payload(self, config):
        dept_id = config.department_id.id if config.department_id else False
        payload = {"updated_at": fields.Datetime.now().isoformat()}
        if config.show_team_score:
            payload["team_score"] = self.get_team_score(dept_id)
        if config.show_leaderboard:
            payload["leaderboard"] = self.get_leaderboard(dept_id)
        if config.show_badges_feed:
            payload["recent_badges"] = self.get_recent_badges(dept_id)
        if config.show_challenges:
            payload["active_challenges"] = self.get_active_challenges(dept_id)
        if config.show_course_completions:
            payload["course_completions"] = self.get_recent_completions(dept_id)
        return payload
