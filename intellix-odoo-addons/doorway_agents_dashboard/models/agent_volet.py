# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayAgentVolet(models.Model):
    _name = "doorway.agent.volet"
    _description = "Volet opérationnel d'un agent IA"
    _order = "sequence, id"

    agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    code = fields.Selection(
        [
            ("reception", "Réception"),
            ("qualification", "Lead qualification"),
            ("cold_call", "Appel à froid"),
        ],
        string="Volet",
        required=True,
    )
    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    prompt_hint = fields.Text(
        string="Consigne volet",
        help="Instructions spécifiques envoyées à n8n / ElevenLabs pour ce volet.",
    )

    _sql_constraints = [
        (
            "agent_volet_code_uniq",
            "unique(agent_id, code)",
            "Chaque volet ne peut être défini qu'une fois par agent.",
        ),
    ]

    def _compute_name(self):
        labels = dict(self._fields["code"].selection)
        for rec in self:
            rec.name = labels.get(rec.code, rec.code or "")
