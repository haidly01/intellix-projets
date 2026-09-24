# -*- coding: utf-8 -*-
from odoo import api, models


class DoorwayOnboardingService(models.AbstractModel):
    _inherit = "doorway.onboarding.service"

    @api.model
    def home_vicidial_call_center(self):
        user = self.env.user
        if user.has_group("doorway_vicidial_campaigns.group_vicidial_qualifier"):
            return self.env["ir.actions.actions"]._for_xml_id(
                "doorway_vicidial_campaigns.action_vicidial_workstation"
            )
        if user.has_group("doorway_vicidial_campaigns.group_vicidial_supervisor"):
            return self.env["ir.actions.actions"]._for_xml_id(
                "doorway_vicidial_campaigns.action_supervisor_dashboard"
            )
        return self.env["ir.actions.actions"]._for_xml_id(
            "doorway_vicidial_campaigns.action_calls_coaching_dashboard"
        )
