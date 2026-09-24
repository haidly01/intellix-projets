# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwayAiPricing(models.Model):
    _name = "doorway.ai.pricing"
    _description = "Grille tarifaire services IA"
    _rec_name = "service"

    service = fields.Selection(
        [
            ("claude_analysis", "Analyse Claude (appel)"),
            ("claude_report", "Rapport post-appel Claude"),
            ("elevenlabs_voice", "ElevenLabs (minute)"),
            ("twilio_call", "Twilio (minute appel)"),
            ("twilio_sms", "Twilio (SMS)"),
            ("n8n_workflow", "Workflow n8n"),
            ("sofia_es_call", "Sofia ES — appel vocal"),
        ],
        required=True,
    )
    real_cost = fields.Float(string="Coût réel USD", digits=(16, 4))
    client_price = fields.Float(string="Prix client USD", digits=(16, 4))
    unit = fields.Char(string="Unité")

    _service_uniq = models.Constraint("unique(service)", "Un tarif par service.")

    @api.model
    def get_pricing(self, service):
        """Retourne dict real_cost, client_price pour un service."""
        row = self.search([("service", "=", service)], limit=1)
        if not row:
            return {"real_cost": 0.0, "client_price": 0.0}
        return {"real_cost": row.real_cost, "client_price": row.client_price}
