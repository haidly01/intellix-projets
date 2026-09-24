# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayAgentIa(models.Model):
    _name = "doorway.agent.ia"
    _description = "Agent vocal IA Doorway"
    _order = "pipeline, agent_type, name"

    name = fields.Char(required=True)
    code = fields.Char(index=True)
    pipeline = fields.Selection(
        [
            ("renovation", "Rénovation"),
            ("driven", "Driven"),
            ("marketing", "Marketing"),
            ("assurance", "Assurance"),
        ],
        required=True,
    )
    agent_type = fields.Selection(
        [
            ("inbound", "Entrant"),
            ("outbound", "Sortant"),
            ("followup", "Suivi"),
        ],
        required=True,
    )
    elevenlabs_voice_id = fields.Char(string="ElevenLabs Voice ID")
    elevenlabs_agent_id = fields.Char(string="ElevenLabs Agent ID")
    twilio_phone_number = fields.Char(string="Numéro Twilio")
    twilio_webhook_url = fields.Char(string="URL Webhook Twilio")
    langue = fields.Selection(
        [
            ("fr", "Français (QC)"),
            ("en", "English"),
            ("multilingual", "Multilingue"),
        ],
        default="fr",
    )
    is_active = fields.Boolean(default=True)
    call_count = fields.Integer(compute="_compute_stats")
    avg_quality_score = fields.Float(compute="_compute_stats", digits=(16, 2))
    system_prompt = fields.Text(string="Prompt système / script")
    session_ids = fields.One2many(
        "doorway.call.session", "legacy_agent_ia_id", string="Sessions"
    )
    profile_id = fields.Many2one("doorway.agent.profile", string="Profil unifié")

    def _compute_stats(self):
        Report = self.env["doorway.call.report"]
        for rec in self:
            reports = Report.search(
                [
                    "|",
                    ("session_id.legacy_agent_ia_id", "=", rec.id),
                    ("session_id.agent_id", "=", rec.profile_id.id),
                ]
            )
            rec.call_count = len(reports)
            rec.avg_quality_score = (
                sum(reports.mapped("score_global")) / len(reports) if reports else 0.0
            )
