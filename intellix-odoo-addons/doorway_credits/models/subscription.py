# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwaySubscription(models.Model):
    _name = "doorway.subscription"
    _description = "Abonnement mensuel Doorway SaaS"
    _rec_name = "tenant_id"

    tenant_id = fields.Many2one("doorway.tenant", required=True, ondelete="cascade")
    price_per_user = fields.Float(default=89.0, string="Prix USD / utilisateur")
    user_count = fields.Integer(default=1)
    monthly_total = fields.Float(compute="_compute_total", store=True, digits=(16, 2))
    billing_day = fields.Integer(default=1)
    next_billing_date = fields.Date()
    last_billing_date = fields.Date()
    stripe_subscription_id = fields.Char(index=True)
    status = fields.Selection(
        [
            ("active", "Actif"),
            ("past_due", "Paiement en retard"),
            ("cancelled", "Annulé"),
            ("trialing", "Période d'essai"),
        ],
        default="trialing",
    )

    @api.depends("user_count", "price_per_user")
    def _compute_total(self):
        for rec in self:
            rec.monthly_total = round(rec.user_count * rec.price_per_user, 2)
