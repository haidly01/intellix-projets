# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayTrafficLog(models.Model):
    _name = "doorway.traffic.log"
    _description = "Historique actions Traffic Manager"
    _order = "create_date desc"

    campaign_id = fields.Many2one("doorway.traffic.campaign", ondelete="set null")
    action = fields.Char(required=True)
    source = fields.Selection(
        [
            ("human", "Humain"),
            ("ai_applied", "IA appliquée"),
            ("ai_ignored", "IA ignorée"),
            ("sync", "Synchronisation"),
            ("system", "Système"),
        ],
        default="system",
    )
    details = fields.Text()
    user_id = fields.Many2one(
        "res.users", default=lambda self: self.env.uid, readonly=True
    )
