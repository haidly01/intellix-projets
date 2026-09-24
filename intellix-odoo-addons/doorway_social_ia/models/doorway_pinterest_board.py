# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayPinterestBoard(models.Model):
    _name = "doorway.pinterest.board"
    _description = "Tableau Pinterest"

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        "doorway.social.account",
        required=True,
        ondelete="cascade",
        domain=[("platform", "=", "pinterest")],
    )
    external_board_id = fields.Char("ID Pinterest")
