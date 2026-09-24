# -*- coding: utf-8 -*-
from odoo import api, models


class PeOnboardingService(models.AbstractModel):
    _name = "pe.onboarding.service"
    _description = "Navigation People Engine (délègue à doorway.onboarding)"

    @api.model
    def action_open_home(self):
        return self.env["doorway.onboarding.service"].action_open_home("people_engine")

    @api.model
    def action_open_wizard(self):
        return self.env["doorway.onboarding.service"].action_open_wizard("people_engine")

    @api.model
    def _action_default_dashboard(self):
        """Ouvre le tableau de bord PE adapté au RÔLE de l'utilisateur.

        - Gestionnaire / RH / Admin → vue d'ensemble GLOBALE (superviseur).
        - Employé standard → son hub personnel ("Bonjour, …").
        Le fallback reste le hub personnel si l'action globale est absente.
        """
        user = self.env.user
        is_supervisor = user.has_group("people_engine.group_manager")
        is_hr = user.has_group("people_engine.group_hr")
        if is_supervisor or is_hr:
            action = self.env.ref(
                "people_engine.action_pe_rh_global", raise_if_not_found=False
            )
            if action:
                return action.read()[0]
            return self.env["pe.employee.profile"].action_open_team_profiles()
        xmlid = "people_engine.action_pe_rh_hub"
        action = self.env.ref(xmlid, raise_if_not_found=False)
        if not action:
            action = self.env.ref(
                "people_engine.action_pe_rh_hub", raise_if_not_found=False
            )
        if not action:
            return {"type": "ir.actions.act_window_close"}
        if action._name == "ir.actions.server":
            return action.run()
        return action.read()[0]

    @api.model
    def _mark_onboarding_done(self):
        self.env["doorway.onboarding.service"]._mark_onboarding_done("people_engine")

    @api.model
    def award_onboarding_badge(self):
        tour = self.env["doorway.onboarding.service"]._get_tour("people_engine")
        if tour:
            return self.env["doorway.onboarding.service"].award_tour_reward(tour)
        return {}
