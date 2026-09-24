# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeopleEngineEnrollment(models.Model):
    _name = "pe.enrollment"
    _description = "Inscription cours People Engine"
    _rec_name = "display_name"
    _order = "date_enrolled desc"

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    course_id = fields.Many2one("pe.course", required=True, ondelete="restrict")
    path_id = fields.Many2one("pe.learning.path", ondelete="set null")
    display_name = fields.Char(compute="_compute_display_name", store=True)

    status = fields.Selection(
        [
            ("not_started", "Non démarré"),
            ("in_progress", "En cours"),
            ("completed", "Complété"),
            ("failed", "Échec quiz"),
            ("expired", "Expiré"),
        ],
        default="not_started",
    )
    progress_percent = fields.Integer(default=0)
    time_spent_hours = fields.Float(default=0.0)
    date_enrolled = fields.Date(default=fields.Date.context_today)
    date_started = fields.Datetime()
    date_completed = fields.Datetime()
    date_deadline = fields.Date()
    quiz_attempts = fields.Integer(default=0)
    best_quiz_score = fields.Integer(default=0)
    last_quiz_score = fields.Integer(default=0)
    quiz_passed = fields.Boolean(default=False)
    certificate_number = fields.Char()
    certificate_date = fields.Date()
    points_awarded = fields.Integer(default=0)
    badge_awarded = fields.Boolean(default=False)
    employee_notes = fields.Text()
    employee_rating = fields.Selection(
        [
            ("1", "1 étoile"),
            ("2", "2 étoiles"),
            ("3", "3 étoiles"),
            ("4", "4 étoiles"),
            ("5", "5 étoiles"),
        ],
    )

    @api.depends("employee_id", "course_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s — %s" % (
                rec.employee_id.name or "?",
                rec.course_id.title or "?",
            )

    def action_start(self):
        self.write(
            {
                "status": "in_progress",
                "date_started": fields.Datetime.now(),
                "progress_percent": max(self.progress_percent, 1),
            }
        )

    def action_complete_course(self, quiz_score=None):
        self.ensure_one()
        return self.complete_course(self.id, quiz_score=quiz_score)

    @api.model
    def complete_course(self, enrollment_id, quiz_score=None):
        enrollment = self.browse(enrollment_id)
        enrollment.ensure_one()
        course = enrollment.course_id

        if course.quiz_id and quiz_score is not None:
            enrollment.last_quiz_score = int(quiz_score)
            enrollment.quiz_attempts += 1
            if quiz_score > enrollment.best_quiz_score:
                enrollment.best_quiz_score = int(quiz_score)
            if quiz_score < course.passing_score:
                enrollment.status = "failed"
                return {
                    "success": False,
                    "reason": "quiz_failed",
                    "score": quiz_score,
                    "required": course.passing_score,
                }
            enrollment.quiz_passed = True

        enrollment.write(
            {
                "status": "completed",
                "date_completed": fields.Datetime.now(),
                "progress_percent": 100,
            }
        )

        if course.points_on_completion:
            self.env["pe.gamification.engine"].award_points(
                enrollment.profile_id.id,
                course.points_on_completion,
                "training",
                _("Cours complété : %s") % course.title,
            )
            enrollment.points_awarded = course.points_on_completion

        if course.badge_on_completion_id and not enrollment.badge_awarded:
            self.env["pe.badge.award"].create(
                {
                    "badge_id": course.badge_on_completion_id.id,
                    "profile_id": enrollment.profile_id.id,
                    "awarded_by_system": True,
                    "reason": _("Complétion du cours : %s") % course.title,
                    "manager_approved": not course.badge_on_completion_id.requires_manager_approval,
                }
            )
            enrollment.badge_awarded = True

        cert = enrollment._generate_certificate_number()
        enrollment.write(
            {
                "certificate_number": cert,
                "certificate_date": fields.Date.context_today(enrollment),
            }
        )
        enrollment._notify_manager_completion()
        enrollment._update_path_progress()
        return {"success": True, "certificate": cert}

    def _generate_certificate_number(self):
        seq = self.env["ir.sequence"].next_by_code("pe.certificate") or "0000"
        return "PE-%s-%s" % (fields.Date.today().year, seq)

    def _notify_manager_completion(self):
        self.ensure_one()
        manager = self.profile_id.employee_id.parent_id
        if manager and manager.user_id:
            self.env["mail.activity"].sudo().create(
                {
                    "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                    "summary": _("Formation complétée : %s") % self.course_id.title,
                    "note": _("%s a terminé le cours.") % self.employee_id.name,
                    "user_id": manager.user_id.id,
                    "res_model_id": self.env["ir.model"]._get("pe.enrollment").id,
                    "res_id": self.id,
                }
            )

    def _update_path_progress(self):
        if self.path_id:
            self.path_id._recompute_progress_from_enrollments()
