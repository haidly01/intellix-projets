# -*- coding: utf-8 -*-
from odoo import fields, models


class PeScoreRefreshWizard(models.TransientModel):
    _name = "pe.score.refresh.wizard"
    _description = "Recalcul des scores People Engine"

    profile_ids = fields.Many2many(
        "pe.employee.profile",
        string="Profils",
        required=True,
    )
    period_days = fields.Selection(
        [
            ("7", "7 jours"),
            ("30", "30 jours"),
            ("90", "90 jours"),
        ],
        default="30",
        required=True,
    )
    manual_quality_score = fields.Float(
        string="Note qualité gestionnaire /10",
        help="Optionnel — sinon score IA ou neutre.",
    )

    def action_refresh(self):
        self.profile_ids.write({"metric_period_days": self.period_days})
        quality = self.manual_quality_score if self.manual_quality_score else None
        self.profile_ids.action_refresh_metrics()
        self.profile_ids.action_calculate_score(
            manual_quality_score=quality,
            calculated_by="manual",
        )
        return {"type": "ir.actions.act_window_close"}
