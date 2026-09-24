# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PeopleEngineGamificationEngine(models.AbstractModel):
    _name = "pe.gamification.engine"
    _description = "Moteur gamification People Engine"

    @api.model
    def _get_or_create_employee_level(self, profile):
        Level = self.env["pe.employee.level"]
        rec = Level.search([("profile_id", "=", profile.id)], limit=1)
        if not rec:
            rec = Level.create({"profile_id": profile.id, "total_points": 0})
        return rec

    @api.model
    def award_points(self, profile_id, points, source, description, reference_id=0):
        profile = self.env["pe.employee.profile"].browse(profile_id)
        if profile.exists():
            self._add_points(profile, points, source, description, reference_id)

    @api.model
    def _add_points(self, profile, points, source, description, reference_id=0):
        if not points:
            return
        el = self._get_or_create_employee_level(profile)
        el.total_points += points
        self.env["pe.point.transaction"].create(
            {
                "employee_level_id": el.id,
                "points": points,
                "source": source,
                "description": description,
                "reference_id": reference_id,
            }
        )
        self._sync_level(el)

    @api.model
    def _sync_level(self, employee_level):
        levels = self.env["pe.level"].search([], order="points_required desc")
        for level in levels:
            if employee_level.total_points >= level.points_required:
                employee_level.level_id = level.id
                break

    @api.model
    def _meets_criterion(self, badge, profile, previous_score):
        ct = badge.criterion_type
        val = badge.criterion_value or 0
        if ct == "score_above":
            return profile.score_global >= val
        if ct == "score_improvement":
            return previous_score is not None and (profile.score_global - previous_score) >= val
        if ct == "crm_conversion":
            return profile.crm_conversion_rate >= val
        if ct == "crm_revenue":
            return profile.crm_revenue_generated >= val
        if ct == "project_ontime":
            return profile.project_ontime_rate >= val
        if ct == "ia_quality":
            return profile.ia_avg_quality_score >= val
        if ct == "objective_complete":
            done = profile.objective_ids.filtered(lambda o: o.status == "achieved")
            return len(done) >= int(val)
        return False

    @api.model
    def check_and_award_badges(self, profile, previous_score=None):
        Badge = self.env["pe.badge"]
        Award = self.env["pe.badge.award"]
        existing = set(
            Award.search([("profile_id", "=", profile.id)]).mapped("badge_id").ids
        )
        created = Award
        for badge in Badge.search(
            [("active", "=", True), ("auto_award", "=", True), ("criterion_type", "!=", "manual")]
        ):
            if badge.id in existing:
                continue
            if self._meets_criterion(badge, profile, previous_score):
                created |= Award.create(
                    {
                        "badge_id": badge.id,
                        "profile_id": profile.id,
                        "awarded_by_system": True,
                        "reason": _("Critère automatique : %s") % badge.criterion_type,
                        "manager_approved": not badge.requires_manager_approval,
                    }
                )
        return created

    @api.model
    def _add_points_for_badge(self, award):
        badge = award.badge_id
        profile = award.profile_id
        if award.manager_approved:
            self._add_points(
                profile,
                badge.points_value,
                "badge",
                _("Badge : %s") % badge.name,
                award.id,
            )
            user = profile.user_id
            bonus = badge.karma_bonus
            if bonus and user and not user.share and hasattr(user, "_add_karma"):
                try:
                    user.sudo()._add_karma(
                        bonus, None, _("Badge PE : %s") % badge.name
                    )
                except Exception:
                    pass

    @api.model
    def award_challenge_winners(self, challenge):
        _t = _
        profiles = challenge.participant_ids
        if not profiles:
            return
        metric = challenge.metric
        scores = []
        for profile in profiles:
            val = self._metric_value(profile, metric)
            scores.append((profile, val))
        scores.sort(key=lambda x: x[1], reverse=True)
        if not scores:
            return
        winner, winner_score = scores[0]
        self._add_points(
            winner,
            challenge.winner_points,
            "challenge",
            _t("Gagnant défi : %s") % challenge.name,
            challenge.id,
        )
        for profile, val in scores:
            if val >= challenge.target_value:
                self._add_points(
                    profile,
                    challenge.participation_points,
                    "challenge",
                    _t("Participation défi : %s") % challenge.name,
                    challenge.id,
                )

    @api.model
    def _metric_value(self, profile, metric):
        mapping = {
            "crm_conversion": profile.crm_conversion_rate,
            "crm_revenue": profile.crm_revenue_generated,
            "tasks_ontime": profile.project_ontime_rate,
            "ia_quality": profile.ia_avg_quality_score,
            "score_global": profile.score_global,
            "appels": profile.appels_jour,
            "demos": profile.demos_bookees_jour,
            "ventes": profile.ventes_jour,
            "score_ia": profile.score_ia_moy_jour,
            "presence": profile.activity_login_days,
        }
        return mapping.get(metric, 0.0)

    @api.model
    def award_call_log_points(self, call_log):
        """Barème Call Center — toujours via add_points."""
        profile = call_log.profile_id
        if not profile:
            profile = self.env["pe.employee.profile"].search(
                [("employee_id", "=", call_log.employee_id.id)], limit=1
            )
        if not profile:
            return 0
        pts = 10
        if call_log.outcome == "demo_bookee":
            pts += 25
        elif call_log.outcome == "vendu":
            pts += 150
        if call_log.ai_score and call_log.ai_score >= 95:
            pts += 40
        elif call_log.ai_score and call_log.ai_score >= 80:
            pts += 20
        self._add_points(
            profile,
            pts,
            "call_center",
            _("Appel %s — %s")
            % (
                call_log.date_call,
                dict(call_log._fields["outcome"].selection).get(
                    call_log.outcome, call_log.outcome
                ),
            ),
            call_log.id,
        )
        profile.refresh_daily_cc_stats()
        return pts

    @api.model
    def check_callcenter_badges(self, profile, call_log=None):
        """Vérifie les badges Call Center après un appel."""
        Badge = self.env["pe.badge"]
        Award = self.env["pe.badge.award"]
        existing = set(
            Award.search([("profile_id", "=", profile.id)]).mapped("badge_id").ids
        )
        created = Award
        cc_badges = Badge.search(
            [
                ("active", "=", True),
                ("auto_award", "=", True),
                (
                    "criterion_type",
                    "in",
                    [
                        "cc_first_sale",
                        "cc_demos_day",
                        "cc_calls_day",
                        "cc_ai_score_avg",
                        "cc_ai_perfect",
                        "cc_monthly_objective",
                        "cc_weekly_rank",
                        "cc_sale_after_18h",
                        "cc_training_complete",
                        "cc_presence_streak",
                        "cc_team_help",
                    ],
                ),
            ]
        )
        for badge in cc_badges:
            if badge.id in existing:
                continue
            if self._meets_cc_criterion(badge, profile, call_log):
                created |= Award.create(
                    {
                        "badge_id": badge.id,
                        "profile_id": profile.id,
                        "awarded_by_system": True,
                        "reason": _("Badge Call Center : %s") % badge.name,
                        "manager_approved": not badge.requires_manager_approval,
                    }
                )
        for award in created:
            self._add_points_for_badge(award)
        return created

    @api.model
    def _meets_cc_criterion(self, badge, profile, call_log=None):
        ct = badge.criterion_type
        val = badge.criterion_value or 0
        if ct == "cc_first_sale":
            return profile.ventes_jour >= 1 or (
                self.env["pe.call.log"].search_count(
                    [
                        ("profile_id", "=", profile.id),
                        ("outcome", "=", "vendu"),
                    ]
                )
                >= 1
            )
        if ct == "cc_demos_day":
            return profile.demos_bookees_jour >= val
        if ct == "cc_calls_day":
            return profile.appels_jour >= val
        if ct == "cc_ai_score_avg":
            logs = self.env["pe.call.log"].search(
                [("profile_id", "=", profile.id), ("ai_score", ">", 0)],
                order="date_call desc",
                limit=int(val) or 20,
            )
            if len(logs) < (int(val) or 20):
                return False
            return sum(logs.mapped("ai_score")) / len(logs) >= 90
        if ct == "cc_ai_perfect" and call_log:
            return call_log.ai_score >= 100
        if ct == "cc_weekly_rank":
            return profile.cc_rank_semaine == int(val or 1)
        if ct == "cc_sale_after_18h":
            hour = int(val or 18)
            log = self.env["pe.call.log"].search(
                [
                    ("profile_id", "=", profile.id),
                    ("outcome", "=", "vendu"),
                ],
                order="date_call desc",
                limit=1,
            )
            return bool(log and log.date_call and log.date_call.hour >= hour)
        if ct == "cc_training_complete":
            Enrollment = self.env.get("pe.enrollment")
            if not Enrollment:
                return False
            enrollments = Enrollment.sudo().search(
                [("profile_id", "=", profile.id)]
            )
            return bool(enrollments) and all(
                e.state == "completed" for e in enrollments
            )
        if ct == "cc_presence_streak":
            summaries = self.env["pe.presence.summary"].sudo().search(
                [
                    ("employee_id", "=", profile.employee_id.id),
                    ("statut_jour", "=", "present"),
                ],
                order="date desc",
                limit=int(val or 30),
            )
            return len(summaries) >= int(val or 30)
        if ct == "cc_monthly_objective" and profile.department_pe_id:
            import datetime

            today = fields.Date.today()
            debut = today.replace(day=1)
            fin = today
            pct_vals = []
            for obj in profile.department_pe_id.objective_ids.filtered(
                lambda o: o.periode == "mois" and o.actif
            ):
                result = obj.evaluer_employe(profile.employee_id.id, debut, fin)
                if result.get("pct_atteinte"):
                    pct_vals.append(result["pct_atteinte"])
            if not pct_vals:
                return False
            return sum(pct_vals) / len(pct_vals) >= float(val or 150)
        if ct == "cc_team_help":
            return False
        return False
