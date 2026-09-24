# -*- coding: utf-8 -*-
from odoo import fields, models


class IntellixPartnerLeadActivity(models.Model):
    _name = "intellix.partner.lead.activity"
    _description = "Activité CRM lead partenaire (Appel / Tâche / RDV)"
    _order = "scheduled_at asc, id asc"

    mandate_id = fields.Many2one(
        "intellix.partner.lead.mandate",
        string="Lead",
        required=True,
        ondelete="cascade",
        index=True,
    )
    activity_type = fields.Selection(
        [("call", "Appel"), ("task", "Tâche"), ("meeting", "RDV")],
        string="Type",
        required=True,
        default="call",
    )
    title = fields.Char(required=True)
    scheduled_at = fields.Datetime(required=True, default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", string="Assigné à")
    done = fields.Boolean(default=False)
