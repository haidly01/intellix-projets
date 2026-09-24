# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AgentFeedback(models.Model):
    _name = "doorway.agent.feedback"
    _description = "Retour utilisateur sur test agent IA"
    _order = "create_date desc"

    agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent",
        required=True,
        ondelete="cascade",
        index=True,
    )
    test_call_id = fields.Many2one(
        "doorway.agent.test.call",
        string="Appel test",
        ondelete="set null",
        index=True,
    )
    rating = fields.Selection(
        [
            ("1", "1 — Très insatisfait"),
            ("2", "2 — Insatisfait"),
            ("3", "3 — Correct"),
            ("4", "4 — Satisfait"),
            ("5", "5 — Excellent"),
        ],
        string="Note",
        required=True,
    )
    comment = fields.Text(string="Commentaire", required=True)
    issue_tone = fields.Boolean(string="Ton / voix")
    issue_script = fields.Boolean(string="Script / message")
    issue_qualification = fields.Boolean(string="Qualification lead")
    issue_latency = fields.Boolean(string="Latence / fluidité")
    issue_actions = fields.Boolean(string="Actions (SMS, transfert…)")
    issue_other = fields.Boolean(string="Autre")
    user_id = fields.Many2one(
        "res.users",
        string="Évaluateur",
        default=lambda self: self.env.uid,
        readonly=True,
    )
    ai_analysis = fields.Text(string="Analyse IA")
    ai_suggestions_json = fields.Text(string="Suggestions IA (JSON)")

    def _issue_labels(self):
        mapping = [
            ("issue_tone", "Ton / voix"),
            ("issue_script", "Script / message"),
            ("issue_qualification", "Qualification lead"),
            ("issue_latency", "Latence / fluidité"),
            ("issue_actions", "Actions automatisées"),
            ("issue_other", "Autre"),
        ]
        return [label for field, label in mapping if getattr(self, field)]

    @api.model
    def submit_from_web_test(self, test_call_id, rating, comment, issues=None):
        """Enregistre le retour utilisateur après un test web."""
        test_call = self.env["doorway.agent.test.call"].browse(int(test_call_id)).exists()
        if not test_call:
            raise UserError(_("Appel test introuvable."))
        issues = issues or {}
        vals = {
            "agent_id": test_call.agent_id.id,
            "test_call_id": test_call.id,
            "rating": str(rating),
            "comment": (comment or "").strip(),
            "issue_tone": bool(issues.get("tone")),
            "issue_script": bool(issues.get("script")),
            "issue_qualification": bool(issues.get("qualification")),
            "issue_latency": bool(issues.get("latency")),
            "issue_actions": bool(issues.get("actions")),
            "issue_other": bool(issues.get("other")),
        }
        if not vals["comment"]:
            raise UserError(_("Veuillez décrire ce qui doit être amélioré."))
        feedback = self.create(vals)
        test_call.write(
            {
                "user_rating": vals["rating"],
                "user_feedback_comment": vals["comment"],
            }
        )
        return {"feedback_id": feedback.id, "status": "ok"}

    def action_run_ai_assist(self):
        """Génère des suggestions d'amélioration à partir du retour utilisateur."""
        for rec in self:
            rec._run_ai_assist()
        return True

    def _run_ai_assist(self):
        self.ensure_one()
        from odoo.addons.doorway_agents_dashboard.services.claude_service import (
            ClaudeService,
        )

        test_call = self.test_call_id
        transcript = test_call.transcript if test_call else ""
        result = ClaudeService(self.env).analyze_with_user_feedback(
            transcript=transcript,
            user_comment=self.comment,
            rating=int(self.rating or 3),
            issue_tags=self._issue_labels(),
            current_prompt=(
                test_call._get_effective_script_prompt()
                if test_call and hasattr(test_call, "_get_effective_script_prompt")
                else (self.agent_id.system_prompt or "")
            ),
        )
        self.write(
            {
                "ai_analysis": result.get("analysis") or "",
                "ai_suggestions_json": json.dumps(
                    result.get("prompt_suggestions") or [], ensure_ascii=False
                ),
            }
        )
        if result.get("prompt_suggestions"):
            self.agent_id.write(
                {
                    "performance_weaknesses_json": json.dumps(
                        result.get("weaknesses") or [], ensure_ascii=False
                    ),
                    "performance_suggestions_json": json.dumps(
                        result.get("prompt_suggestions") or [], ensure_ascii=False
                    ),
                    "performance_analysis_at": fields.Datetime.now(),
                }
            )
        return result

    @api.model
    def list_for_agent(self, agent_id, limit=20):
        rows = self.search(
            [("agent_id", "=", int(agent_id))],
            order="create_date desc",
            limit=int(limit),
        )
        out = []
        for fb in rows:
            try:
                suggestions = json.loads(fb.ai_suggestions_json or "[]")
            except json.JSONDecodeError:
                suggestions = []
            out.append(
                {
                    "id": fb.id,
                    "date": fields.Datetime.to_string(fb.create_date),
                    "rating": int(fb.rating or 0),
                    "comment": fb.comment,
                    "issues": fb._issue_labels(),
                    "user": fb.user_id.name,
                    "ai_analysis": fb.ai_analysis or "",
                    "ai_suggestions": suggestions,
                    "test_call_id": fb.test_call_id.id or False,
                }
            )
        return out
