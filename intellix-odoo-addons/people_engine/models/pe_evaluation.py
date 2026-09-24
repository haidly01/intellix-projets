# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class PeopleEngineEvaluation(models.Model):
    _name = "pe.evaluation"
    _description = "Évaluation formelle People Engine"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    name = fields.Char(compute="_compute_name", store=True)
    evaluation_type = fields.Selection(
        [
            ("periodic", "Évaluation périodique"),
            ("probation", "Fin de probation"),
            ("promotion", "Évaluation promotion"),
            ("improvement", "Plan d'amélioration"),
            ("recognition", "Reconnaissance"),
            ("disciplinary", "Mesure disciplinaire"),
        ],
        required=True,
        default="periodic",
        tracking=True,
    )
    period_start = fields.Date()
    period_end = fields.Date()
    evaluator_id = fields.Many2one("hr.employee", required=True, string="Évaluateur")
    pe_score_at_evaluation = fields.Float(string="Score PE au moment de l'évaluation")
    pe_score_previous = fields.Float()
    pe_trend = fields.Char()
    strengths = fields.Text(string="Points forts")
    improvements = fields.Text(string="Axes d'amélioration")
    action_plan = fields.Text(string="Plan d'action")
    manual_score = fields.Float(string="Note évaluateur /10")
    recommendation = fields.Selection(
        [
            ("praise", "Félicitations"),
            ("coach", "Coaching recommandé"),
            ("warn", "Avertissement"),
            ("pip", "Plan d'amélioration"),
            ("promote", "Promotion recommandée"),
            ("terminate", "Mise à pied recommandée"),
        ],
        tracking=True,
    )
    status = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("pending_review", "En attente révision RH"),
            ("pending_approval", "En attente approbation DG"),
            ("approved", "Approuvé"),
            ("communicated", "Communiqué à l'employé"),
            ("completed", "Complété"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        tracking=True,
    )
    hr_reviewer_id = fields.Many2one("hr.employee", string="Réviseur RH")
    hr_reviewed_date = fields.Datetime()
    hr_comments = fields.Text()
    dg_approver_id = fields.Many2one("hr.employee", string="Approbateur DG")
    dg_approved_date = fields.Datetime()
    dg_comments = fields.Text()
    legal_basis = fields.Text(
        string="Base légale",
        help="Requis pour mesures disciplinaires et mise à pied.",
    )
    legal_article_ids = fields.Many2many(
        "pe.legal.article",
        string="Articles droit du travail",
        help="Références informatives — ne remplace pas un avis juridique.",
    )
    legal_jurisdiction_code = fields.Char(
        string="Code juridiction",
        default="QC",
        help="QC, FR, ON, etc.",
    )

    def action_suggest_legal_articles(self):
        self.ensure_one()
        action_map = {
            "disciplinary": "formal_warn",
            "improvement": "pip",
            "periodic": "coaching",
        }
        action_type = action_map.get(self.evaluation_type, "coaching")
        articles = self.env["pe.legal.engine"].get_relevant_articles(
            action_type, self.legal_jurisdiction_code or "QC"
        )
        self.legal_article_ids = [(6, 0, articles.ids)]
        return True
    employee_acknowledged = fields.Boolean(default=False)
    employee_acknowledged_date = fields.Datetime()
    employee_comments = fields.Text()

    @api.depends("employee_id", "evaluation_type", "period_end")
    def _compute_name(self):
        for rec in self:
            emp = rec.employee_id.name or "Employé"
            etype = dict(rec._fields["evaluation_type"].selection).get(
                rec.evaluation_type, ""
            )
            rec.name = f"{emp} — {etype}"

    def _check_disciplinary_access(self):
        if self.evaluation_type in ("disciplinary",) or self.recommendation in (
            "warn",
            "pip",
            "terminate",
        ):
            if not self.env.user.has_group("people_engine.group_hr"):
                raise AccessError(
                    _("Les évaluations disciplinaires requièrent le groupe RH People Engine.")
                )

    def action_submit_for_hr_review(self):
        self._check_disciplinary_access()
        for rec in self:
            if rec.evaluation_type == "disciplinary" and not rec.legal_basis:
                raise UserError(
                    _("La base légale est obligatoire pour une mesure disciplinaire.")
                )
            rec.write({"status": "pending_review"})

    def action_hr_approve(self):
        self.ensure_one()
        self._check_disciplinary_access()
        self.write(
            {
                "status": "pending_approval",
                "hr_reviewer_id": self.env.user.employee_id.id,
                "hr_reviewed_date": fields.Datetime.now(),
            }
        )

    def action_dg_approve(self):
        self.ensure_one()
        self.write(
            {
                "status": "approved",
                "dg_approver_id": self.env.user.employee_id.id,
                "dg_approved_date": fields.Datetime.now(),
            }
        )

    def action_complete(self):
        for rec in self:
            rec.write({"status": "completed"})
            self.env["pe.action.log"].log_action(
                rec.profile_id,
                "evaluation_completed",
                _("Évaluation complétée : %s") % rec.name,
                actor_type="hr" if self.env.user.has_group("people_engine.group_hr") else "manager",
                evaluation_id=rec.id,
                score_before=rec.pe_score_previous,
                score_after=rec.pe_score_at_evaluation,
            )
