# -*- coding: utf-8 -*-
from odoo import fields, models


class PeEvaluationWizard(models.TransientModel):
    _name = "pe.evaluation.wizard"
    _description = "Wizard évaluation formelle"

    profile_id = fields.Many2one("pe.employee.profile", required=True)
    employee_id = fields.Many2one(related="profile_id.employee_id")
    evaluation_type = fields.Selection(
        [
            ("periodic", "Évaluation périodique"),
            ("probation", "Fin de probation"),
            ("promotion", "Évaluation promotion"),
            ("improvement", "Plan d'amélioration"),
            ("recognition", "Reconnaissance"),
            ("disciplinary", "Mesure disciplinaire"),
        ],
        default="periodic",
        required=True,
    )
    evaluator_id = fields.Many2one(
        "hr.employee",
        required=True,
        default=lambda self: self.env.user.employee_id,
    )
    period_start = fields.Date()
    period_end = fields.Date()
    manual_score = fields.Float(string="Note /10")
    strengths = fields.Text()
    improvements = fields.Text()
    recommendation = fields.Selection(
        [
            ("praise", "Félicitations"),
            ("coach", "Coaching recommandé"),
            ("warn", "Avertissement"),
            ("pip", "Plan d'amélioration"),
            ("promote", "Promotion recommandée"),
            ("terminate", "Mise à pied recommandée"),
        ]
    )
    legal_basis = fields.Text()

    def action_create_evaluation(self):
        self.ensure_one()
        profile = self.profile_id
        evaluation = self.env["pe.evaluation"].create(
            {
                "profile_id": profile.id,
                "evaluation_type": self.evaluation_type,
                "evaluator_id": self.evaluator_id.id,
                "period_start": self.period_start,
                "period_end": self.period_end,
                "manual_score": self.manual_score,
                "strengths": self.strengths,
                "improvements": self.improvements,
                "recommendation": self.recommendation,
                "legal_basis": self.legal_basis,
                "pe_score_at_evaluation": profile.score_global,
                "pe_score_previous": profile.score_global,
                "pe_trend": profile.score_trend,
                "status": "draft",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "pe.evaluation",
            "res_id": evaluation.id,
            "view_mode": "form",
            "target": "current",
        }
