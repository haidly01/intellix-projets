# -*- coding: utf-8 -*-
"""Moteur de calcul des scores People Engine."""


class PeopleEngineScoreEngine:
    WEIGHTS = {
        "performance": {
            "total": 40,
            "objectives": 40,
            "quality": 0,
            "impact": 0,
        },
        "engagement": {
            "total": 30,
            "participation": 10,
            "collaboration": 10,
            "process": 10,
        },
        "growth": {
            "total": 30,
            "progression": 10,
            "training": 10,
            "development": 10,
        },
    }

    def __init__(self, env):
        self.env = env
        self._load_weights_from_config()

    def _load_weights_from_config(self):
        ICP = self.env["ir.config_parameter"].sudo()
        for key in ("performance", "engagement", "growth"):
            val = ICP.get_param(f"people_engine.weight_{key}")
            if val:
                try:
                    self.WEIGHTS[key]["total"] = float(val)
                except ValueError:
                    pass

    @staticmethod
    def _weighted_objective_achievement(objectives):
        """Taux d'atteinte moyen pondéré (0-100) sur les objectifs actifs."""
        if not objectives:
            return 0.0
        total_weight = sum(objectives.mapped("weight")) or len(objectives)
        if not total_weight:
            return 0.0
        weighted_sum = sum(
            (obj.achievement_rate or 0.0) * (obj.weight or 1.0) for obj in objectives
        )
        return weighted_sum / total_weight

    def calculate_score(self, profile, metrics, manual_quality_score=None):
        scores = {}
        objectives = profile.objective_ids.filtered(lambda o: o.status == "active")
        perf_total = self.WEIGHTS["performance"]["total"]
        avg_achievement = self._weighted_objective_achievement(objectives)
        scores["objectives"] = avg_achievement / 100.0 * perf_total
        scores["quality"] = 0.0
        scores["impact"] = 0.0
        scores["performance_total"] = scores["objectives"]

        scores["participation"] = min(
            (metrics.get("activity_messages", 0) or profile.activity_messages_sent)
            / 50
            * 10,
            10,
        )
        scores["collaboration"] = min(
            (metrics.get("activity_completed", 0) or profile.activity_tasks_created)
            / 20
            * 10,
            10,
        )
        ontime_rate = metrics.get("project_ontime_rate", 0) or profile.project_ontime_rate
        scores["process"] = ontime_rate / 100 * 10

        scores["engagement_total"] = (
            scores["participation"] + scores["collaboration"] + scores["process"]
        )

        previous_obj_pct = self._get_previous_objective_achievement_pct(profile, perf_total)
        if previous_obj_pct is not None:
            delta = avg_achievement - previous_obj_pct
            scores["progression"] = min(max(5 + delta / 10.0, 0), 10)
        else:
            scores["progression"] = min(avg_achievement / 100.0 * 10, 10)

        scores["training"] = self._compute_training_score(profile)
        scores["development"] = self._compute_development_score(profile)

        scores["growth_total"] = (
            scores["progression"] + scores["training"] + scores["development"]
        )
        scores["global"] = (
            scores["performance_total"]
            + scores["engagement_total"]
            + scores["growth_total"]
        )
        scores["objectives_achievement_pct"] = avg_achievement
        return scores

    def _compute_training_score(self, profile):
        enrollments = self.env["pe.enrollment"].search([("profile_id", "=", profile.id)])
        enrollment_score = 0.0
        if enrollments:
            completed = len(enrollments.filtered(lambda e: e.status == "completed"))
            partial = sum(
                (e.progress_percent or 0) / 100.0
                for e in enrollments.filtered(lambda e: e.status == "in_progress")
            )
            rate = (completed + partial) / len(enrollments)
            enrollment_score = min(rate * 10, 10)
        quiz_bonus = 0.0
        if profile.employee_id and "pe.quiz.attempt" in self.env:
            month_pts = self.env["pe.quiz.assignment"].collect_croissance_quiz_points(
                profile.employee_id.id
            )
            quiz_bonus = min(month_pts / 1.5, 10.0)
        return min(enrollment_score + quiz_bonus, 10.0)

    def _compute_development_score(self, profile):
        paths = self.env["pe.learning.path"].search(
            [
                ("profile_id", "=", profile.id),
                ("status", "in", ["active", "completed"]),
            ]
        )
        if paths:
            avg = sum(paths.mapped("completion_percent")) / len(paths)
            return min(avg / 100.0 * 10, 10)
        dev_objectives = profile.objective_ids.filtered(
            lambda o: o.status == "active" and o.objective_type == "custom"
        )
        if dev_objectives:
            avg = self._weighted_objective_achievement(dev_objectives)
            return min(avg / 100.0 * 10, 10)
        return 0.0

    def _get_previous_objective_achievement_pct(self, profile, perf_total):
        previous = self.env["pe.performance.score"].search(
            [("profile_id", "=", profile.id)],
            order="period_end desc",
            limit=1,
        )
        if not previous:
            return None
        if previous.score_performance_total and perf_total:
            return previous.score_performance_total / perf_total * 100.0
        if previous.score_objectives and perf_total:
            return previous.score_objectives / perf_total * 100.0
        return None

    def _get_previous_score(self, profile):
        previous = self.env["pe.performance.score"].search(
            [("profile_id", "=", profile.id)],
            order="period_end desc",
            limit=2,
        )
        if len(previous) >= 2:
            return previous[1].score_global
        if len(previous) == 1:
            return previous[0].score_global
        return None

    def detect_alerts(self, profile, scores):
        alerts = []
        global_score = scores.get("global", 0)
        if global_score < 40:
            alerts.append(
                {
                    "level": "critical",
                    "type": "low_performance",
                    "message": (
                        f"Score critique : {global_score:.1f}/100. "
                        "Intervention gestionnaire recommandée."
                    ),
                }
            )
        elif global_score < 60:
            alerts.append(
                {
                    "level": "warning",
                    "type": "below_average",
                    "message": f"Performance sous la moyenne : {global_score:.1f}/100.",
                }
            )
        if scores.get("process", 10) < 4:
            alerts.append(
                {
                    "level": "warning",
                    "type": "deadline_issues",
                    "message": (
                        "Taux de respect des délais faible. "
                        "Vérifier la charge de travail."
                    ),
                }
            )
        previous = self._get_previous_score(profile)
        if previous is not None and (global_score - previous) < -10:
            alerts.append(
                {
                    "level": "warning",
                    "type": "declining_trend",
                    "message": (
                        f"Baisse significative du score : {previous:.1f} → {global_score:.1f}"
                    ),
                }
            )
        return alerts
