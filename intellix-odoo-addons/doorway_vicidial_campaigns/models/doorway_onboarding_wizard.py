# -*- coding: utf-8 -*-
from odoo import api, models


class DoorwayOnboardingWizard(models.TransientModel):
    _inherit = "doorway.onboarding.wizard"

    @api.depends("current_step_key", "tour_id")
    def _compute_current_step(self):
        super()._compute_current_step()
        for wiz in self.filtered(
            lambda w: w.tour_id.code == "vicidial_call_center"
            and w.current_step_key == "welcome"
        ):
            presentation = self.env[
                "doorway.vicidial.onboarding.service"
            ].get_claude_presentation_html()
            wiz.step_body_html = (presentation or "") + (wiz.step_body_html or "")
