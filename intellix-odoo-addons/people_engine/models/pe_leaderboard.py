# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import _, api, fields, models


class PeopleEngineLeaderboard(models.Model):
    _name = "pe.leaderboard"
    _description = "Classement People Engine"
    _order = "period_end desc"

    name = fields.Char(compute="_compute_name", store=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    state = fields.Selection(
        [("draft", "Brouillon"), ("published", "Publié")],
        default="draft",
    )
    line_ids = fields.One2many("pe.leaderboard.line", "leaderboard_id")
    participant_count = fields.Integer(compute="_compute_stats", store=True)
    top_score = fields.Float(compute="_compute_stats", store=True)

    @api.depends("period_start", "period_end")
    def _compute_name(self):
        for rec in self:
            if rec.period_start and rec.period_end:
                rec.name = _("Classement %s → %s") % (
                    rec.period_start,
                    rec.period_end,
                )
            else:
                rec.name = _("Classement People Engine")

    @api.depends("line_ids", "line_ids.score_global")
    def _compute_stats(self):
        for rec in self:
            rec.participant_count = len(rec.line_ids)
            rec.top_score = max(rec.line_ids.mapped("score_global") or [0.0])

    def action_publish(self):
        self.write({"state": "published"})

    def action_rebuild_lines(self):
        for board in self:
            board.line_ids.unlink()
            profiles = self.env["pe.employee.profile"].search(
                [("pe_status", "!=", "inactive")],
                order="score_global desc",
            )
            rank = 0
            for profile in profiles:
                rank += 1
                self.env["pe.leaderboard.line"].create(
                    {
                        "leaderboard_id": board.id,
                        "profile_id": profile.id,
                        "rank": rank,
                        "score_global": profile.score_global,
                    }
                )

    @api.model
    def _cron_monthly_leaderboard(self):
        today = date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(day=31)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        board = self.create(
            {
                "period_start": start,
                "period_end": end,
                "state": "published",
            }
        )
        board.action_rebuild_lines()
        return True


class PeopleEngineLeaderboardLine(models.Model):
    _name = "pe.leaderboard.line"
    _description = "Ligne classement People Engine"
    _order = "rank asc"

    leaderboard_id = fields.Many2one(
        "pe.leaderboard", required=True, ondelete="cascade", index=True
    )
    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade"
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    rank = fields.Integer(required=True)
    score_global = fields.Float(string="Score /100")
    badge_award_count = fields.Integer(
        related="profile_id.badge_award_count",
        string="Badges PE",
    )
