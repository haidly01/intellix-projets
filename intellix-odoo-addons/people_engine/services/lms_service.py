# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_LMS_PATH_PROMPT = """Tu es un expert RH en développement des compétences.
Génère un parcours de formation personnalisé. Réponds UNIQUEMENT en JSON valide :
{
  "path_name": "Nom du parcours",
  "duration_weeks": 6,
  "rationale": "Explication 2-3 phrases",
  "courses": [{"course_id": 1, "week": 1, "priority": "high", "reason": "..."}],
  "success_criteria": "...",
  "expected_score_improvement": 8
}
"""


class PeopleEngineLMSService(models.AbstractModel):
    _name = "pe.lms.service"
    _description = "Service LMS People Engine"

    @api.model
    def generate_learning_path_with_claude(self, profile, path_type="performance"):
        profile.ensure_one()
        courses = self.env["pe.course"].search([("is_active", "=", True)])
        courses_list = "\n".join(
            "- ID:%s | %s | %s | %sh | %s"
            % (c.id, c.title, c.category, c.duration_hours, c.difficulty)
            for c in courses
        )
        ctx = """
Employé : %s
Poste : %s
Score global : %.1f/100 (Perf %.1f / Eng %.1f / Croissance %.1f)
CRM conversion : %.1f%% | Projet on-time : %.1f%% | IA qualité : %.1f/10
Type parcours : %s
""" % (
            profile.employee_id.name,
            profile.employee_id.job_id.name or "—",
            profile.score_global,
            profile.score_performance,
            profile.score_engagement,
            profile.score_growth,
            profile.crm_conversion_rate,
            profile.project_ontime_rate,
            profile.ia_avg_quality_score,
            path_type,
        )
        prompt = "PROFIL:\n%s\n\nCOURS DISPONIBLES:\n%s\n" % (ctx, courses_list)
        path_data = {}
        if self._ai_available():
            system = self.env["renovation.ai.service"]._get_prompt(
                "pe_lms_path", DEFAULT_LMS_PATH_PROMPT
            )
            try:
                answer = self.env["renovation.ai.service"]._call(
                    [{"role": "user", "content": prompt}],
                    system=system,
                    max_tokens=1200,
                    purpose="pe_lms_path",
                )
                path_data = self._parse_json(answer)
            except UserError:
                raise
            except Exception as exc:
                _logger.exception("PE LMS path generation")
                path_data = self._fallback_path_data(profile, courses, path_type)
        else:
            path_data = self._fallback_path_data(profile, courses, path_type)

        manager = profile.employee_id.parent_id
        if not manager:
            manager = self.env.user.employee_id
        if not manager:
            raise UserError(_("Aucun gestionnaire associé pour valider le parcours."))

        path = self.env["pe.learning.path"].create(
            {
                "name": path_data.get("path_name")
                or _("Parcours — %s") % profile.employee_id.name,
                "profile_id": profile.id,
                "path_type": path_type,
                "duration_weeks": path_data.get("duration_weeks", 4),
                "claude_generated": self._ai_available(),
                "claude_rationale": path_data.get("rationale", ""),
                "manager_id": manager.id,
                "status": "pending",
                "date_start": fields.Date.today(),
            }
        )
        course_ids = [
            int(c["course_id"])
            for c in path_data.get("courses", [])
            if c.get("course_id") in courses.ids
        ]
        if not course_ids and courses:
            course_ids = courses[:3].ids
        path.write(
            {
                "course_ids": [(6, 0, course_ids)],
                "course_order": json.dumps(course_ids),
            }
        )
        return path

    @api.model
    def _ai_available(self):
        if "renovation.ai.service" not in self.env:
            return False
        return self.env["renovation.ai.service"]._available()

    @api.model
    def _parse_json(self, text):
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group())
        return {}

    @api.model
    def _fallback_path_data(self, profile, courses, path_type):
        selected = courses.filtered(lambda c: c.category in ("crm", "project"))[:3]
        if not selected:
            selected = courses[:3]
        return {
            "path_name": _("Parcours %s (hors ligne)") % path_type,
            "duration_weeks": 4,
            "rationale": _("Sélection automatique — IA indisponible."),
            "courses": [{"course_id": c.id} for c in selected],
        }

    @api.model
    def get_mandatory_courses_for_employee(self, profile):
        job_id = profile.employee_id.job_id.id
        mandatory = self.env["pe.course"].search(
            [
                ("is_active", "=", True),
                "|",
                ("is_mandatory", "=", True),
                ("mandatory_by_role_ids", "in", [job_id] if job_id else []),
            ]
        )
        completed = self.env["pe.enrollment"].search(
            [
                ("profile_id", "=", profile.id),
                ("status", "=", "completed"),
            ]
        ).mapped("course_id").ids
        return mandatory.filtered(lambda c: c.id not in completed)

    @api.model
    def _cron_check_mandatory_overdue(self):
        Profile = self.env["pe.employee.profile"]
        for profile in Profile.search([("pe_status", "!=", "inactive")]):
            missing = self.get_mandatory_courses_for_employee(profile)
            if missing:
                self.env["pe.action.log"].log_action(
                    profile,
                    "status_changed",
                    _("Formations obligatoires non complétées : %s")
                    % ", ".join(missing.mapped("title")),
                    actor_type="system",
                )
