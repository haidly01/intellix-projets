# -*- coding: utf-8 -*-
from odoo import fields, models


class IntellixSupportDiagnostic(models.Model):
    _name = "intellix.support.diagnostic"
    _description = "Exécution diagnostic support"
    _order = "create_date desc"

    ticket_id = fields.Many2one(
        "intellix.support.ticket",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(related="ticket_id.partner_id", store=True)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("done", "Terminé"),
            ("failed", "Échec"),
        ],
        default="done",
    )
    side_origin = fields.Selection(
        [
            ("unknown", "Non déterminé"),
            ("client", "Côté client"),
            ("platform", "Côté Intellix"),
        ],
        default="unknown",
    )
    summary_html = fields.Html(string="Résumé")
    result_json = fields.Text(string="Résultat brut (JSON)")
    checks_passed = fields.Integer()
    checks_failed = fields.Integer()
    checks_warning = fields.Integer()
