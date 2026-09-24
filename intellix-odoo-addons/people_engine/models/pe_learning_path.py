# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineLearningPath(models.Model):
    _name = "pe.learning.path"
    _description = "Parcours de formation personnalisé"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(required=True, tracking=True)
    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    path_type = fields.Selection(
        [
            ("onboarding", "Intégration nouveau"),
            ("performance", "Amélioration performance"),
            ("promotion", "Préparation promotion"),
            ("compliance", "Conformité obligatoire"),
            ("custom", "Parcours personnalisé"),
        ],
        default="performance",
    )
    coaching_plan_id = fields.Many2one("pe.coaching.plan", ondelete="set null")
    course_ids = fields.Many2many(
        "pe.course",
        "pe_learning_path_course_rel",
        "path_id",
        "course_id",
        string="Cours du parcours",
    )
    course_order = fields.Text(help="JSON : ordre des cours [id, ...]")
    date_start = fields.Date()
    date_end = fields.Date()
    duration_weeks = fields.Integer(default=4)
    total_courses = fields.Integer(compute="_compute_progress", store=True)
    completed_courses = fields.Integer(compute="_compute_progress", store=True)
    completion_percent = fields.Float(compute="_compute_progress", store=True)
    claude_generated = fields.Boolean(default=False)
    claude_rationale = fields.Text()
    manager_id = fields.Many2one("hr.employee", required=True)
    manager_approved = fields.Boolean(default=False)
    manager_approved_date = fields.Datetime()
    status = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("pending", "En attente approbation"),
            ("active", "En cours"),
            ("completed", "Complété"),
            ("expired", "Expiré"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        tracking=True,
    )
    completion_points = fields.Integer(default=100)
    completion_badge_id = fields.Many2one("pe.badge")
    completion_prime_rule_id = fields.Many2one(
        "pe.prime.rule",
        string="Règle prime à l'achèvement",
        help="Prime proposée (brouillon) si parcours complété — validation séparée.",
    )
    enrollment_ids = fields.One2many("pe.enrollment", "path_id")

    @api.depends("course_ids", "enrollment_ids", "enrollment_ids.status")
    def _compute_progress(self):
        for path in self:
            path.total_courses = len(path.course_ids)
            completed = path.enrollment_ids.filtered(lambda e: e.status == "completed")
            path.completed_courses = len(
                completed.filtered(lambda e: e.course_id in path.course_ids)
            )
            path.completion_percent = (
                (path.completed_courses / path.total_courses * 100)
                if path.total_courses
                else 0.0
            )

    def _recompute_progress_from_enrollments(self):
        for path in self:
            if path.completion_percent >= 100 and path.status == "active":
                path._on_path_completed()

    def _on_path_completed(self):
        self.ensure_one()
        self.write({"status": "completed"})
        if self.completion_points:
            self.env["pe.gamification.engine"].award_points(
                self.profile_id.id,
                self.completion_points,
                "training",
                _("Parcours complété : %s") % self.name,
            )
        self.env["pe.action.log"].log_action(
            self.profile_id,
            "evaluation_completed",
            _("Parcours formation complété : %s") % self.name,
            actor_type="system",
        )

    def action_manager_approve(self):
        for path in self:
            if path.status != "pending":
                raise UserError(_("Seuls les parcours en attente peuvent être approuvés."))
            path.write(
                {
                    "manager_approved": True,
                    "manager_approved_date": fields.Datetime.now(),
                    "status": "active",
                    "date_start": path.date_start or fields.Date.today(),
                }
            )
            path._create_enrollments()

    def _create_enrollments(self):
        Enrollment = self.env["pe.enrollment"]
        for path in self:
            order = []
            if path.course_order:
                try:
                    order = json.loads(path.course_order)
                except (json.JSONDecodeError, TypeError):
                    order = path.course_ids.ids
            else:
                order = path.course_ids.ids
            for course_id in order:
                if not Enrollment.search(
                    [
                        ("profile_id", "=", path.profile_id.id),
                        ("course_id", "=", course_id),
                        ("path_id", "=", path.id),
                    ],
                    limit=1,
                ):
                    Enrollment.create(
                        {
                            "profile_id": path.profile_id.id,
                            "course_id": course_id,
                            "path_id": path.id,
                        }
                    )

    def action_generate_claude(self):
        self.ensure_one()
        return self.env["pe.lms.service"].generate_learning_path_with_claude(
            self.profile_id, self.path_type or "performance"
        )
