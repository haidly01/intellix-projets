# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayCreditAlert(models.Model):
    _name = "doorway.credit.alert"
    _description = "Alerte crédits / abonnement"
    _order = "create_date desc"

    tenant_id = fields.Many2one("doorway.tenant", required=True, ondelete="cascade")
    alert_type = fields.Selection(
        [
            ("low_balance", "Solde bas"),
            ("payment_failed", "Paiement échoué"),
            ("daily_limit", "Plafond journalier"),
            ("suspended", "Compte suspendu"),
        ],
        required=True,
    )
    message = fields.Text(required=True)
    is_read = fields.Boolean(default=False)
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Avertissement"), ("critical", "Critique")],
        default="warning",
    )
