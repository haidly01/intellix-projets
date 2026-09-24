# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayTrafficChannel(models.Model):
    _name = "doorway.traffic.channel"
    _description = "Canal publicitaire"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Selection(
        [
            ("meta", "Meta Ads"),
            ("google", "Google Ads"),
            ("tiktok", "TikTok Ads"),
            ("linkedin", "LinkedIn Ads"),
            ("youtube", "YouTube Ads"),
            ("backlink", "Backlink"),
            ("annuaire", "Annuaire"),
        ],
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
