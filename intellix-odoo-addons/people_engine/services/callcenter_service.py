# -*- coding: utf-8 -*-
import logging
from datetime import date, datetime, time, timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PeCallcenterService(models.AbstractModel):
    _name = "pe.callcenter.service"
    _description = "Service Call Center People Engine"

    @api.model
    def refresh_leaderboards(self, department_id=None):
        """Recalcule les classements journalier / hebdo / mensuel."""
        Profile = self.env["pe.employee.profile"].sudo()
        domain = [("department_pe_id", "!=", False)]
        if department_id:
            domain.append(("department_pe_id", "=", department_id))
        profiles = Profile.search(domain)
        periods = [
            ("day", fields.Date.today()),
            ("week", fields.Date.today() - timedelta(days=fields.Date.today().weekday())),
            ("month", fields.Date.today().replace(day=1)),
        ]
        for period_key, period_start in periods:
            scores = []
            for profile in profiles:
                pts = self._points_for_period(profile, period_start, period_key)
                scores.append((profile, pts))
            scores.sort(key=lambda x: x[1], reverse=True)
            for rank, (profile, pts) in enumerate(scores, start=1):
                if period_key == "day":
                    profile.write({"cc_rank_jour": rank, "points_jour": pts})
                elif period_key == "week":
                    profile.write({"cc_rank_semaine": rank, "points_semaine": pts})
        return True

    @api.model
    def _points_for_period(self, profile, period_start, period_key):
        txs = self.env["pe.point.transaction"].sudo().search(
            [
                ("profile_id", "=", profile.id),
                ("source", "=", "call_center"),
            ]
        )
        today = fields.Date.today()
        total = 0
        for tx in txs:
            if not tx.date:
                continue
            d = fields.Datetime.to_datetime(tx.date).date()
            if period_key == "day" and d == today:
                total += tx.points
            elif period_key == "week" and d >= period_start:
                total += tx.points
            elif period_key == "month" and d >= period_start:
                total += tx.points
        return total

    @api.model
    def check_daily_objectives(self):
        """23:55 — attribue points si objectifs journaliers atteints."""
        today = fields.Date.today()
        start = datetime.combine(today, time.min)
        end = datetime.combine(today, time.max)
        engine = self.env["pe.gamification.engine"]
        Objective = self.env["pe.department.objective"]
        departments = self.env["pe.department"].search(
            [("is_template", "=", False), ("work_type", "in", ("mixte", "qualification"))]
        )
        for dept in departments:
            for obj in Objective.search(
                [
                    ("department_id", "=", dept.id),
                    ("periode", "=", "jour"),
                    ("actif", "=", True),
                ]
            ):
                for emp in dept.employee_ids:
                    result = obj.evaluer_employe(emp.id, start, end)
                    if result.get("atteint") and obj.points_atteint:
                        profile = self.env["pe.employee.profile"].search(
                            [("employee_id", "=", emp.id)], limit=1
                        )
                        if profile:
                            engine._add_points(
                                profile,
                                obj.points_atteint,
                                "objective",
                                _("Objectif atteint : %s") % obj.name,
                                obj.id,
                            )
        return True

    @api.model
    def generate_daily_challenges(self):
        """08:00 — crée les défis du jour par département actif."""
        Challenge = self.env["pe.challenge"].sudo()
        today = fields.Date.today()
        departments = self.env["pe.department"].search(
            [("is_template", "=", False), ("work_type", "in", ("mixte", "qualification"))]
        )
        hr_emp = self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid)], limit=1
        )
        if not hr_emp:
            hr_emp = self.env["hr.employee"].search([], limit=1)
        for dept in departments:
            obj_appels = dept.objective_ids.filtered(
                lambda o: o.metrique == "appels_total_jour" and o.periode == "jour"
            )[:1]
            target = obj_appels.valeur_cible if obj_appels else 80
            existing = Challenge.search(
                [
                    ("department_pe_id", "=", dept.id),
                    ("date_start", "=", today),
                    ("metric", "=", "appels"),
                ],
                limit=1,
            )
            if not existing:
                Challenge.create(
                    {
                        "name": _("Objectif du jour — %s") % dept.name,
                        "description": _("Défi quotidien Call Center"),
                        "challenge_type": "individual",
                        "metric": "appels",
                        "target_value": target,
                        "date_start": today,
                        "date_end": today,
                        "winner_points": 50,
                        "participation_points": 10,
                        "status": "active",
                        "created_by_id": hr_emp.id,
                        "approved_by_id": hr_emp.id,
                        "department_pe_id": dept.id,
                        "participant_ids": [
                            (
                                6,
                                0,
                                self.env["pe.employee.profile"]
                                .search([("employee_id", "in", dept.employee_ids.ids)])
                                .ids,
                            )
                        ],
                    }
                )
        return True

    @api.model
    def get_wall_dashboard_data(self):
        """Données écran mural TV Call Center."""
        Profile = self.env["pe.employee.profile"].sudo()
        profiles = Profile.search(
            [("department_pe_id", "!=", False)],
            order="points_jour desc",
            limit=10,
        )
        leaderboard = []
        for profile in profiles:
            leaderboard.append(
                {
                    "name": profile.display_name,
                    "points": profile.points_jour,
                    "demos": profile.demos_bookees_jour,
                    "appels": profile.appels_jour,
                    "rank": profile.cc_rank_jour,
                    "status": profile.cc_status,
                }
            )
        BadgeAward = self.env["pe.badge.award"].sudo()
        recent_badges = BadgeAward.search(
            [],
            order="award_date desc",
            limit=8,
        )
        badges = [
            {
                "employee": a.employee_id.name,
                "badge": a.badge_id.name,
                "icon": a.badge_id.icon,
                "date": fields.Datetime.to_string(a.award_date),
            }
            for a in recent_badges
        ]
        Challenge = self.env["pe.challenge"].sudo()
        today = fields.Date.today()
        challenge = Challenge.search(
            [
                ("status", "=", "active"),
                ("date_start", "<=", today),
                ("date_end", ">=", today),
            ],
            limit=1,
        )
        challenge_data = None
        if challenge:
            profile = profiles[:1]
            current = profile.appels_jour if profile else 0
            challenge_data = {
                "name": challenge.name,
                "current": current,
                "target": challenge.target_value,
                "pct": min(
                    100,
                    int(current / challenge.target_value * 100)
                    if challenge.target_value
                    else 0,
                ),
            }
        on_call = Profile.search_count([("cc_status", "=", "on_call")])
        demos_today = sum(profiles.mapped("demos_bookees_jour"))
        return {
            "refreshed_at": fields.Datetime.to_string(fields.Datetime.now()),
            "leaderboard": leaderboard,
            "recent_badges": badges,
            "challenge": challenge_data,
            "stats": {
                "on_call": on_call,
                "demos_today": demos_today,
                "agents_online": Profile.search_count(
                    [("cc_status", "in", ("online", "on_call"))]
                ),
            },
        }
