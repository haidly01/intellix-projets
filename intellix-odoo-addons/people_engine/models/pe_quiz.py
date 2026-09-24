# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PeopleEngineQuiz(models.Model):
    _name = "pe.quiz"
    _description = "Quiz de certification People Engine"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nom du quiz", required=True, tracking=True)
    description = fields.Text(string="Description")
    category = fields.Selection(
        [
            ("product", "Produit / Marché"),
            ("crm", "CRM IntelliX"),
            ("ia_agent", "Agent IA"),
            ("hr", "RH & Processus"),
            ("compliance", "Conformité & Légal"),
            ("other", "Autre"),
        ],
        string="Catégorie",
        required=True,
        default="product",
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "Actif"),
            ("archived", "Archivé"),
        ],
        string="Statut",
        default="draft",
        tracking=True,
    )
    passing_score = fields.Integer(
        string="Score de réussite (%)",
        default=80,
        help="Pourcentage minimum pour être certifié (ex: 80 = 80%)",
    )
    max_attempts = fields.Integer(
        string="Tentatives maximum",
        default=3,
        help="0 = illimité",
    )
    time_limit = fields.Integer(
        string="Temps limite (minutes)",
        default=0,
        help="0 = pas de limite",
    )
    randomize_questions = fields.Boolean(
        string="Mélanger les questions",
        default=True,
    )
    show_correct_answers = fields.Boolean(
        string="Afficher les bonnes réponses après",
        default=True,
    )
    croissance_points = fields.Integer(
        string="Points Croissance accordés",
        default=5,
        help="Points ajoutés via gamification si quiz passé avec succès",
    )
    required_for_campaign = fields.Boolean(
        string="Requis avant accès aux campagnes",
        default=False,
    )
    campaign_ids = fields.Many2many(
        "doorway.campaign",
        "pe_quiz_campaign_rel",
        "quiz_id",
        "campaign_id",
        string="Campagnes conditionnées",
    )
    course_id = fields.Many2one(
        "pe.course",
        string="Cours lié",
        ondelete="set null",
        help="Cours LMS associé (optionnel)",
    )
    question_ids = fields.One2many("pe.quiz.question", "quiz_id", string="Questions")
    question_count = fields.Integer(compute="_compute_counts", string="Nombre de questions")
    attempt_ids = fields.One2many("pe.quiz.attempt", "quiz_id", string="Tentatives")
    attempt_count = fields.Integer(compute="_compute_counts", string="Tentatives totales")
    certified_count = fields.Integer(compute="_compute_counts", string="Agents certifiés")
    assignment_ids = fields.One2many("pe.quiz.assignment", "quiz_id", string="Assignations")
    created_by = fields.Many2one(
        "res.users",
        string="Créé par",
        default=lambda self: self.env.user,
    )
    created_date = fields.Date(
        string="Date de création",
        default=fields.Date.context_today,
    )

    @api.depends("question_ids", "attempt_ids", "attempt_ids.passed", "attempt_ids.is_best_attempt")
    def _compute_counts(self):
        for quiz in self:
            quiz.question_count = len(quiz.question_ids)
            quiz.attempt_count = len(quiz.attempt_ids)
            quiz.certified_count = len(
                quiz.attempt_ids.filtered(lambda a: a.passed and a.is_best_attempt)
            )

    def action_activate(self):
        for quiz in self:
            if not quiz.question_ids:
                raise UserError(_("Ajoutez au moins une question avant d'activer le quiz."))
            quiz.state = "active"

    def action_archive(self):
        self.write({"state": "archived"})

    def action_draft(self):
        self.write({"state": "draft"})

    def action_view_attempts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tentatives — %s") % self.name,
            "res_model": "pe.quiz.attempt",
            "view_mode": "list,form",
            "domain": [("quiz_id", "=", self.id)],
            "context": {"default_quiz_id": self.id},
        }

    def action_view_certified(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Certifiés — %s") % self.name,
            "res_model": "pe.quiz.attempt",
            "view_mode": "list,form",
            "domain": [
                ("quiz_id", "=", self.id),
                ("passed", "=", True),
                ("is_best_attempt", "=", True),
            ],
        }

    def action_start_quiz(self):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Ce quiz n'est pas actif."))
        return {
            "type": "ir.actions.client",
            "tag": "pe_quiz_player",
            "name": self.name,
            "params": {"quiz_id": self.id},
        }

    @api.model
    def get_player_context(self, quiz_id):
        """Bootstrap QuizPlayer — employé courant + quota tentatives."""
        quiz = self.browse(quiz_id)
        if not quiz.exists():
            raise UserError(_("Quiz introuvable."))
        if quiz.state != "active":
            raise UserError(_("Ce quiz n'est pas actif."))
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_("Aucun employé associé à votre compte utilisateur."))
        finished = self.env["pe.quiz.attempt"].search_count(
            [
                ("quiz_id", "=", quiz.id),
                ("employee_id", "=", employee.id),
                ("state", "in", ("completed", "timed_out")),
            ]
        )
        in_progress = self.env["pe.quiz.attempt"].search(
            [
                ("quiz_id", "=", quiz.id),
                ("employee_id", "=", employee.id),
                ("state", "=", "in_progress"),
            ],
            limit=1,
        )
        max_attempts = quiz.max_attempts or 0
        remaining = None if max_attempts == 0 else max(max_attempts - finished, 0)
        can_start = max_attempts == 0 or finished < max_attempts or bool(in_progress)
        return {
            "quiz_id": quiz.id,
            "employee_id": employee.id,
            "finished_attempts": finished,
            "remaining_attempts": remaining,
            "can_start": can_start,
            "in_progress_attempt_id": in_progress.id if in_progress else False,
        }

    @api.model
    def check_campaign_certification(self, employee_id, campaign_id):
        """Retourne (ok, message) pour la porte campagne."""
        required = self.search(
            [
                ("state", "=", "active"),
                ("required_for_campaign", "=", True),
                ("campaign_ids", "in", [campaign_id]),
            ]
        )
        Attempt = self.env["pe.quiz.attempt"]
        for quiz in required:
            certified = Attempt.search_count(
                [
                    ("quiz_id", "=", quiz.id),
                    ("employee_id", "=", employee_id),
                    ("passed", "=", True),
                    ("is_best_attempt", "=", True),
                ]
            )
            if not certified:
                return False, _("Certification requise : %s") % quiz.name
        return True, ""


class PeopleEngineQuizQuestion(models.Model):
    _name = "pe.quiz.question"
    _description = "Question de quiz People Engine"
    _order = "sequence, id"

    quiz_id = fields.Many2one("pe.quiz", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    question_text = fields.Text(string="Question", required=True)
    explanation = fields.Text(
        string="Explication (affichée après réponse)",
        help="Pourquoi cette réponse est correcte",
    )
    question_type = fields.Selection(
        [
            ("single", "Choix unique"),
            ("multiple", "Choix multiple"),
            ("true_false", "Vrai / Faux"),
        ],
        string="Type",
        default="single",
        required=True,
    )
    category_tag = fields.Selection(
        [
            ("fiche", "Fiche propriété"),
            ("eco", "Écoénergie"),
            ("int", "Réno intérieure"),
            ("ext", "Réno extérieure"),
            ("immo", "Immobilier"),
            ("regles", "Règles & processus"),
            ("crm", "CRM"),
            ("ia", "Agent IA"),
            ("rh", "RH"),
            ("general", "Général"),
        ],
        string="Sous-catégorie",
        default="general",
    )
    points = fields.Integer(string="Points", default=1)
    answer_ids = fields.One2many("pe.quiz.answer", "question_id", string="Réponses")
    correct_answer_count = fields.Integer(
        compute="_compute_correct_count",
        string="Nb réponses correctes",
    )
    legal_article_id = fields.Many2one("pe.legal.article")

    @api.depends("answer_ids.is_correct")
    def _compute_correct_count(self):
        for question in self:
            question.correct_answer_count = len(question.answer_ids.filtered("is_correct"))

    @api.constrains("answer_ids", "question_type")
    def _check_correct_answers(self):
        for question in self:
            if not question.answer_ids:
                continue
            correct = question.answer_ids.filtered("is_correct")
            if question.question_type in ("single", "true_false") and len(correct) != 1:
                raise ValidationError(
                    _("Une question à choix unique doit avoir exactement une bonne réponse.")
                )
            if question.question_type == "multiple" and len(correct) < 1:
                raise ValidationError(
                    _("Une question à choix multiple doit avoir au moins une bonne réponse.")
                )


class PeopleEngineQuizAnswer(models.Model):
    _name = "pe.quiz.answer"
    _description = "Réponse de question quiz"
    _order = "sequence, id"

    question_id = fields.Many2one(
        "pe.quiz.question",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    answer_text = fields.Char(string="Texte de la réponse", required=True)
    is_correct = fields.Boolean(string="Bonne réponse", default=False)


class PeopleEngineQuizAttempt(models.Model):
    _name = "pe.quiz.attempt"
    _description = "Tentative de quiz agent"
    _order = "date_start desc"

    quiz_id = fields.Many2one("pe.quiz", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
        string="Agent",
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one("res.users", string="Utilisateur")
    profile_id = fields.Many2one(
        "pe.employee.profile",
        string="Profil PE",
        compute="_compute_profile_id",
        store=True,
    )
    state = fields.Selection(
        [
            ("in_progress", "En cours"),
            ("completed", "Terminé"),
            ("timed_out", "Temps écoulé"),
        ],
        default="in_progress",
        string="État",
    )
    date_start = fields.Datetime(string="Début", default=fields.Datetime.now)
    date_end = fields.Datetime(string="Fin")
    duration_seconds = fields.Integer(
        string="Durée (secondes)",
        compute="_compute_duration",
        store=True,
    )
    score_pct = fields.Float(string="Score (%)", digits=(5, 2))
    total_questions = fields.Integer(string="Total questions")
    correct_answers = fields.Integer(string="Bonnes réponses")
    passed = fields.Boolean(string="Certifié", default=False)
    attempt_number = fields.Integer(string="Numéro de tentative", default=1)
    is_best_attempt = fields.Boolean(
        string="Meilleure tentative",
        default=False,
        help="True si c'est la tentative avec le meilleur score pour cet agent",
    )
    answer_line_ids = fields.One2many(
        "pe.quiz.attempt.line",
        "attempt_id",
        string="Réponses données",
    )
    pe_score_id = fields.Many2one(
        "pe.performance.score",
        string="Score PE généré",
    )
    points_awarded = fields.Integer(string="Points Croissance accordés", default=0)

    @api.depends("employee_id")
    def _compute_profile_id(self):
        Profile = self.env["pe.employee.profile"]
        for attempt in self:
            profile = Profile.search(
                [("employee_id", "=", attempt.employee_id.id)], limit=1
            )
            attempt.profile_id = profile.id if profile else False

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                delta = rec.date_end - rec.date_start
                rec.duration_seconds = int(delta.total_seconds())
            else:
                rec.duration_seconds = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("quiz_id") and vals.get("employee_id"):
                count = self.search_count(
                    [
                        ("quiz_id", "=", vals["quiz_id"]),
                        ("employee_id", "=", vals["employee_id"]),
                    ]
                )
                vals["attempt_number"] = count + 1
            if not vals.get("user_id"):
                vals["user_id"] = self.env.user.id
        return super().create(vals_list)

    def _update_best_attempt_flag(self):
        for attempt in self:
            domain = [
                ("quiz_id", "=", attempt.quiz_id.id),
                ("employee_id", "=", attempt.employee_id.id),
                ("state", "in", ("completed", "timed_out")),
            ]
            all_attempts = self.search(
                domain, order="score_pct desc, date_start desc"
            )
            all_attempts.write({"is_best_attempt": False})
            if all_attempts:
                all_attempts[0].is_best_attempt = True

    def action_complete(self, correct_count, total_count, timed_out=False):
        """Clôture une tentative et calcule le score."""
        self.ensure_one()
        total_count = total_count or 0
        correct_count = correct_count or 0
        score_pct = (correct_count / total_count * 100.0) if total_count else 0.0
        passed = (not timed_out) and score_pct >= self.quiz_id.passing_score
        self.write(
            {
                "state": "timed_out" if timed_out else "completed",
                "date_end": fields.Datetime.now(),
                "correct_answers": correct_count,
                "total_questions": total_count,
                "score_pct": score_pct,
                "passed": passed,
            }
        )
        self._update_best_attempt_flag()
        if passed and self.is_best_attempt:
            self._award_croissance_points()
            self._sync_course_enrollment()
        return passed

    @api.model
    def action_complete_timeout(self, attempt_id, correct_count, total_count):
        attempt = self.browse(attempt_id)
        attempt.ensure_one()
        return attempt.action_complete(correct_count, total_count, timed_out=True)

    def _award_croissance_points(self):
        self.ensure_one()
        points = self.quiz_id.croissance_points
        if points <= 0 or not self.profile_id:
            return
        existing = self.env["pe.point.transaction"].search_count(
            [
                ("employee_level_id.profile_id", "=", self.profile_id.id),
                ("source", "=", "quiz_certification"),
                ("reference_id", "=", self.id),
            ]
        )
        if existing:
            return
        self.env["pe.gamification.engine"].award_points(
            self.profile_id.id,
            points,
            "quiz_certification",
            _("Certification quiz : %s") % self.quiz_id.name,
            self.id,
        )
        self.points_awarded = points
        pe_score = self.env["pe.performance.score"].search(
            [("profile_id", "=", self.profile_id.id)],
            order="period_end desc",
            limit=1,
        )
        if pe_score:
            self.pe_score_id = pe_score.id

    def _sync_course_enrollment(self):
        self.ensure_one()
        course = self.quiz_id.course_id
        if not course or not self.profile_id:
            return
        enrollment = self.env["pe.enrollment"].search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("course_id", "=", course.id),
            ],
            limit=1,
        )
        if not enrollment:
            enrollment = self.env["pe.enrollment"].create(
                {
                    "profile_id": self.profile_id.id,
                    "course_id": course.id,
                    "status": "in_progress",
                }
            )
        self.env["pe.enrollment"].complete_course(
            enrollment.id, quiz_score=int(self.score_pct)
        )


class PeopleEngineQuizAttemptLine(models.Model):
    _name = "pe.quiz.attempt.line"
    _description = "Ligne de réponse tentative quiz"

    attempt_id = fields.Many2one("pe.quiz.attempt", required=True, ondelete="cascade")
    question_id = fields.Many2one("pe.quiz.question", required=True)
    selected_answer_ids = fields.Many2many(
        "pe.quiz.answer",
        "pe_quiz_attempt_line_answer_rel",
        "line_id",
        "answer_id",
        string="Réponses sélectionnées",
    )
    is_correct = fields.Boolean(string="Correct", default=False)
    points_earned = fields.Integer(string="Points gagnés", default=0)


class PeopleEngineQuizAssignment(models.Model):
    _name = "pe.quiz.assignment"
    _description = "Assignation quiz à un agent ou groupe"
    _order = "date_assigned desc"

    quiz_id = fields.Many2one("pe.quiz", required=True, ondelete="cascade")
    profile_id = fields.Many2one(
        "pe.employee.profile",
        string="Agent",
        ondelete="cascade",
    )
    department_id = fields.Many2one(
        "pe.department",
        string="Département / groupe",
        ondelete="cascade",
    )
    date_assigned = fields.Date(
        string="Date d'assignation",
        default=fields.Date.context_today,
    )
    deadline = fields.Date(string="Échéance")
    mandatory = fields.Boolean(string="Obligatoire", default=True)
    active = fields.Boolean(default=True)

    @api.constrains("profile_id", "department_id")
    def _check_target(self):
        for rec in self:
            if not rec.profile_id and not rec.department_id:
                raise ValidationError(
                    _("Indiquez un agent ou un département pour l'assignation.")
                )

    @api.model
    def collect_croissance_quiz_points(self, employee_id, period_end=None):
        """Points Croissance issus des certifications quiz sur le mois courant."""
        period_end = period_end or fields.Date.context_today(self)
        month_start = period_end.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        attempts = self.env["pe.quiz.attempt"].search(
            [
                ("employee_id", "=", employee_id),
                ("passed", "=", True),
                ("is_best_attempt", "=", True),
                ("date_end", ">=", month_start),
                ("date_end", "<=", month_end),
            ]
        )
        points = sum(a.quiz_id.croissance_points for a in attempts)
        return min(points, 15)
