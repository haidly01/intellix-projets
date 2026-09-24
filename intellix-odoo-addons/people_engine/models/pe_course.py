# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEngineCourse(models.Model):
    _name = "pe.course"
    _description = "Cours de formation People Engine"
    _rec_name = "title"
    _order = "title"

    title = fields.Char(required=True)
    description = fields.Text()
    category = fields.Selection(
        [
            ("crm", "CRM et vente"),
            ("project", "Gestion de projet"),
            ("leadership", "Leadership et management"),
            ("communication", "Communication"),
            ("technical", "Compétences techniques"),
            ("legal", "Droit et conformité"),
            ("ia_tools", "Outils IA et automatisation"),
            ("onboarding", "Intégration nouveaux employés"),
            ("compliance", "Conformité et éthique"),
        ],
        default="crm",
    )
    course_type = fields.Selection(
        [
            ("internal", "Formation interne"),
            ("external", "Formation externe"),
            ("video", "Vidéo en ligne"),
            ("document", "Document / PDF"),
            ("quiz_only", "Quiz d'évaluation"),
            ("live", "Session en direct"),
        ],
        default="internal",
    )
    content_url = fields.Char(string="URL contenu")
    content_html = fields.Html(sanitize_attributes=False)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "pe_course_attachment_rel",
        "course_id",
        "attachment_id",
        string="Documents attachés",
    )
    duration_hours = fields.Float(default=1.0)
    difficulty = fields.Selection(
        [
            ("beginner", "Débutant"),
            ("intermediate", "Intermédiaire"),
            ("advanced", "Avancé"),
        ],
        default="beginner",
    )
    points_on_completion = fields.Integer(default=20)
    badge_on_completion_id = fields.Many2one("pe.badge", string="Badge à l'achèvement")
    quiz_id = fields.Many2one("pe.quiz")
    passing_score = fields.Integer(
        default=70,
        help="Score minimum (%) pour valider le cours",
    )
    prerequisite_ids = fields.Many2many(
        "pe.course",
        "pe_course_prerequisite_rel",
        "course_id",
        "prerequisite_id",
        string="Prérequis",
    )
    legal_article_ids = fields.Many2many(
        "pe.legal.article",
        "pe_course_legal_rel",
        "course_id",
        "article_id",
        string="Articles légaux couverts",
    )
    enrollment_count = fields.Integer(compute="_compute_stats", store=True)
    completion_rate = fields.Float(compute="_compute_stats", store=True)
    avg_quiz_score = fields.Float(compute="_compute_stats", store=True)
    is_active = fields.Boolean(default=True)
    is_mandatory = fields.Boolean(
        default=False,
        help="Obligatoire pour tous les employés actifs",
    )
    mandatory_by_role_ids = fields.Many2many(
        "hr.job",
        "pe_course_job_rel",
        "course_id",
        "job_id",
        string="Obligatoire pour ces postes",
    )

    @api.depends("enrollment_ids", "enrollment_ids.status", "enrollment_ids.last_quiz_score")
    def _compute_stats(self):
        Enrollment = self.env["pe.enrollment"]
        for course in self:
            enrollments = Enrollment.search([("course_id", "=", course.id)])
            course.enrollment_count = len(enrollments)
            if enrollments:
                completed = enrollments.filtered(lambda e: e.status == "completed")
                course.completion_rate = len(completed) * 100.0 / len(enrollments)
                scores = enrollments.filtered(lambda e: e.last_quiz_score).mapped(
                    "last_quiz_score"
                )
                course.avg_quiz_score = sum(scores) / len(scores) if scores else 0.0
            else:
                course.completion_rate = 0.0
                course.avg_quiz_score = 0.0

    enrollment_ids = fields.One2many("pe.enrollment", "course_id")
