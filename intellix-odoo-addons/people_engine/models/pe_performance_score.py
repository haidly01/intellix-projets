# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEnginePerformanceScore(models.Model):
    _name = "pe.performance.score"
    _description = "Score de performance People Engine"
    _order = "period_end desc, id desc"

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    period_type = fields.Selection(
        [
            ("weekly", "Semaine"),
            ("monthly", "Mois"),
            ("quarterly", "Trimestre"),
        ],
        default="monthly",
        required=True,
    )
    score_objectives = fields.Float(string="Objectifs /15")
    score_quality = fields.Float(string="Qualité /15")
    score_business_impact = fields.Float(string="Impact business /10")
    score_performance_total = fields.Float(string="Performance /40")
    score_participation = fields.Float(string="Participation /10")
    score_collaboration = fields.Float(string="Collaboration /10")
    score_process = fields.Float(string="Processus /10")
    score_engagement_total = fields.Float(string="Engagement /30")
    score_progression = fields.Float(string="Progression /10")
    score_training = fields.Float(string="Formations /10")
    score_development = fields.Float(string="Développement /10")
    score_growth_total = fields.Float(string="Croissance /30")
    score_global = fields.Float(string="Score global /100")
    previous_score = fields.Float()
    score_delta = fields.Float(compute="_compute_delta", store=True)
    trend = fields.Selection(
        [
            ("up", "En hausse"),
            ("stable", "Stable"),
            ("down", "En baisse"),
        ],
    )
    calculation_notes = fields.Text()
    calculated_at = fields.Datetime(default=fields.Datetime.now)
    calculated_by = fields.Selection(
        [
            ("auto", "Automatique"),
            ("manual", "Manuel"),
        ],
        default="auto",
    )

    @api.depends("score_global", "previous_score")
    def _compute_delta(self):
        for rec in self:
            if rec.previous_score:
                rec.score_delta = rec.score_global - rec.previous_score
            else:
                rec.score_delta = 0.0
