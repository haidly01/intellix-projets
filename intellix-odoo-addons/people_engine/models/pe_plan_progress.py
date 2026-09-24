# -*- coding: utf-8 -*-
from odoo import fields, models


class PeopleEnginePlanProgress(models.Model):
    _name = "pe.plan.progress"
    _description = "Note de suivi plan de coaching"
    _order = "date desc"

    plan_id = fields.Many2one(
        "pe.coaching.plan", required=True, ondelete="cascade", index=True
    )
    date = fields.Date(default=fields.Date.context_today, required=True)
    author_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    note = fields.Text(required=True)
    score_snapshot = fields.Float(string="Score au moment du suivi")
