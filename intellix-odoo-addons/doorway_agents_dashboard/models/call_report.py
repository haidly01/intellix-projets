# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.doorway_agents_dashboard.services.claude_service import ClaudeService


class DoorwayCallReport(models.Model):
    _name = "doorway.call.report"
    _description = "Rapport post-appel"
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    session_id = fields.Many2one(
        "doorway.call.session", required=True, ondelete="cascade", string="Session"
    )
    agent_id = fields.Many2one(related="session_id.agent_id", store=True)
    lead_id = fields.Many2one(related="session_id.lead_id", store=True)

    score_accroche = fields.Float(digits=(16, 2))
    score_qualification = fields.Float(digits=(16, 2))
    score_objections = fields.Float(digits=(16, 2))
    score_closing = fields.Float(digits=(16, 2))
    score_global = fields.Float(digits=(16, 2), string="Score global")

    points_forts = fields.Text()
    points_amelioration = fields.Text()
    prochaine_action = fields.Selection(
        [
            ("rappel", "Rappel"),
            ("email", "Email"),
            ("rdv", "Rendez-vous"),
            ("archiver", "Archiver"),
        ],
        default="rappel",
    )
    claude_summary = fields.Text(string="Résumé Claude")

    quality_band = fields.Selection(
        [
            ("excellent", "Excellent"),
            ("good", "Bon"),
            ("improve", "À améliorer"),
        ],
        compute="_compute_quality_band",
        store=True,
    )

    @api.depends("session_id", "score_global")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.session_id.name or "Rapport"

    @api.depends("score_global")
    def _compute_quality_band(self):
        for rec in self:
            if rec.score_global >= 8:
                rec.quality_band = "excellent"
            elif rec.score_global >= 6:
                rec.quality_band = "good"
            else:
                rec.quality_band = "improve"

    @api.model
    def create_from_session(self, session):
        """Génère le rapport via Claude à partir de la session."""
        prompt = session.agent_id.system_prompt if session.agent_id else ""
        data = ClaudeService(session.env).analyze_post_call(
            session.transcript or "",
            prompt,
            call_id=session.twilio_call_sid,
        )
        if data.get("error") == "insufficient_credits":
            return self.create(
                {
                    "session_id": session.id,
                    "claude_summary": "Crédits insuffisants pour générer le rapport.",
                    "score_global": 0.0,
                }
            )
        vals = {
            "session_id": session.id,
            "score_accroche": float(data.get("score_accroche", 0) or 0),
            "score_qualification": float(data.get("score_qualification", 0) or 0),
            "score_objections": float(data.get("score_objections", 0) or 0),
            "score_closing": float(data.get("score_closing", 0) or 0),
            "score_global": float(data.get("score_global", 0) or 0),
            "points_forts": data.get("points_forts") or "",
            "points_amelioration": data.get("points_amelioration") or "",
            "prochaine_action": data.get("prochaine_action") or "rappel",
            "claude_summary": data.get("claude_summary") or "",
        }
        return self.create(vals)
