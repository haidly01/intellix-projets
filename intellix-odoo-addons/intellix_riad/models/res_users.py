# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsersRiad(models.Model):
    _inherit = "res.users"

    riad_establishment_ids = fields.Many2many(
        "intellix.riad.establishment",
        "intellix_riad_user_estab_rel",
        "user_id",
        "establishment_id",
        string="Établissements hébergement",
    )
