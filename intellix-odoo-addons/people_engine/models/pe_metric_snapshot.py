# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models


class PeopleEngineMetricSnapshot(models.Model):
    _name = "pe.metric.snapshot"
    _description = "Snapshot métriques People Engine"
    _order = "snapshot_date desc, id desc"

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    snapshot_date = fields.Date(default=fields.Date.context_today, required=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    metrics_json = fields.Text(string="Métriques (JSON)")
    score_global = fields.Float()
    score_performance = fields.Float()
    score_engagement = fields.Float()
    score_growth = fields.Float()

    def set_metrics(self, metrics_dict):
        self.metrics_json = json.dumps(metrics_dict, default=str)

    def get_metrics(self):
        self.ensure_one()
        if not self.metrics_json:
            return {}
        return json.loads(self.metrics_json)
