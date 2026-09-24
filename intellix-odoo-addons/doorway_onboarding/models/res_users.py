# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    doorway_onboarding_state = fields.Json(
        string="Visites guidées Doorway",
        default=dict,
        help="Codes des tours terminés, ex. {'people_engine': true}.",
    )

    def doorway_onboarding_is_done(self, tour_code):
        self.ensure_one()
        state = self.doorway_onboarding_state or {}
        return bool(state.get(tour_code))

    def doorway_onboarding_mark_done(self, tour_code):
        self.ensure_one()
        state = dict(self.doorway_onboarding_state or {})
        state[tour_code] = True
        self.sudo().write({"doorway_onboarding_state": state})
