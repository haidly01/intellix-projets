# -*- coding: utf-8 -*-
from odoo import api, models


class VicidialAgentSession(models.Model):
    _inherit = "doorway.vicidial.agent.session"

    @api.model
    def get_available_campaigns(self, user=None):
        user = (user or self.env.user).sudo()
        if user.demo_call_center:
            return self.env["doorway.campaign"].search(
                [
                    ("state", "in", ("ready", "active")),
                    ("company_id", "in", user.company_ids.ids),
                ],
                order="name asc",
            )
        return super().get_available_campaigns(user=user)
