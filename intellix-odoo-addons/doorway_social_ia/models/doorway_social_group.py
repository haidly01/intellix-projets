# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySocialGroup(models.Model):
    _name = "doorway.social.group"
    _description = "Groupe social (Facebook / LinkedIn)"

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        "doorway.social.account", required=True, ondelete="cascade"
    )
    platform = fields.Selection(
        [("facebook", "Facebook"), ("linkedin", "LinkedIn")],
        required=True,
    )
    external_group_id = fields.Char("ID externe")
