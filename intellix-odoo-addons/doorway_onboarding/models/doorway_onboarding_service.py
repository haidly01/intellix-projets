# -*- coding: utf-8 -*-
import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class DoorwayOnboardingService(models.AbstractModel):
    _name = "doorway.onboarding.service"
    _description = "Service visite guidée Doorway"

    @api.model
    def _get_tour(self, tour_code):
        return self.env["doorway.onboarding.tour"].search(
            [("code", "=", tour_code), ("active", "=", True)], limit=1
        )

    @api.model
    def action_open_home(self, tour_code):
        """Point d'entrée menu racine : wizard si première visite, sinon accueil."""
        user = self.env.user
        if not user.doorway_onboarding_is_done(tour_code):
            return self._action_open_wizard(tour_code)
        return self._action_home_after_tour(tour_code)

    @api.model
    def action_open_wizard(self, tour_code):
        return self._action_open_wizard(tour_code)

    @api.model
    def _action_open_wizard(self, tour_code):
        tour = self._get_tour(tour_code)
        if not tour:
            return self._action_home_after_tour(tour_code)
        return {
            "type": "ir.actions.act_window",
            "name": tour.name,
            "res_model": "doorway.onboarding.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_tour_id": tour.id},
        }

    @api.model
    def _action_home_after_tour(self, tour_code):
        tour = self._get_tour(tour_code)
        if tour and tour.home_action_method:
            method = getattr(self, tour.home_action_method, None)
            if method:
                return method()
        if tour and tour.home_action_xmlid:
            try:
                return self.env["ir.actions.actions"]._for_xml_id(
                    tour.home_action_xmlid
                )
            except ValueError:
                pass
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def home_people_engine(self):
        if self.env["ir.module.module"]._get("people_engine").state == "installed":
            return self.env["pe.onboarding.service"]._action_default_dashboard()
        return {"type": "ir.actions.act_window_close"}

    @api.model
    def _mark_onboarding_done(self, tour_code):
        self.env.user.doorway_onboarding_mark_done(tour_code)

    @api.model
    def award_tour_reward(self, tour):
        """Attribue le badge configuré (PE si disponible) et retourne les infos d'affichage."""
        result = {
            "awarded": False,
            "already_had": False,
            "badge_name": tour.badge_name or tour.name,
            "badge_icon": tour.badge_icon or "🏆",
            "points": tour.reward_points or 0,
            "rarity": "uncommon",
            "message": "",
        }
        if tour.pe_badge_xmlid and self._is_module_installed("people_engine"):
            pe_result = self._award_pe_badge(tour.pe_badge_xmlid)
            if pe_result:
                result.update(pe_result)
                return result

        result["awarded"] = True
        result["message"] = _("Bravo ! Quête %(name)s terminée.") % {"name": tour.name}
        partner = self.env.user.partner_id
        if partner:
            self.env["mail.message"].sudo().create(
                {
                    "model": "res.partner",
                    "res_id": partner.id,
                    "message_type": "notification",
                    "body": _(
                        "🎉 %(icon)s <b>%(badge)s</b> — visite guidée terminée "
                        "(+%(pts)s XP)"
                    )
                    % {
                        "icon": result["badge_icon"],
                        "badge": result["badge_name"],
                        "pts": result["points"],
                    },
                }
            )
        return result

    @api.model
    def _is_module_installed(self, name):
        return (
            self.env["ir.module.module"].search([("name", "=", name)], limit=1).state
            == "installed"
        )

    @api.model
    def _award_pe_badge(self, badge_xmlid):
        badge = self.env.ref(badge_xmlid, raise_if_not_found=False)
        if not badge:
            return None
        employee = self.env.user.employee_id
        if not employee:
            return {
                "awarded": False,
                "message": _("Aucun employé lié à votre compte."),
                "badge_name": badge.name,
                "badge_icon": badge.icon,
                "points": badge.points_value,
                "rarity": badge.rarity,
            }
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if not profile:
            return {
                "awarded": False,
                "message": _("Profil People Engine introuvable."),
                "badge_name": badge.name,
                "badge_icon": badge.icon,
                "points": badge.points_value,
                "rarity": badge.rarity,
            }
        Award = self.env["pe.badge.award"].sudo()
        existing = Award.search(
            [("profile_id", "=", profile.id), ("badge_id", "=", badge.id)], limit=1
        )
        if existing:
            return {
                "awarded": True,
                "already_had": True,
                "badge_name": badge.name,
                "badge_icon": badge.icon,
                "points": badge.points_value,
                "rarity": badge.rarity,
                "message": _("Vous possédez déjà ce badge !"),
            }
        award = Award.create(
            {
                "badge_id": badge.id,
                "profile_id": profile.id,
                "awarded_by_system": True,
                "reason": _("Visite guidée Doorway"),
                "manager_approved": True,
                "is_public": True,
            }
        )
        award._apply_rewards()
        profile.message_post(
            body=_(
                "🎉 Badge débloqué : %(icon)s <b>%(name)s</b> (+%(pts)s points PE)"
            )
            % {"icon": badge.icon, "name": badge.name, "pts": badge.points_value},
            partner_ids=[profile.user_id.partner_id.id]
            if profile.user_id.partner_id
            else [],
            message_type="notification",
        )
        return {
            "awarded": True,
            "already_had": False,
            "badge_name": badge.name,
            "badge_icon": badge.icon,
            "points": badge.points_value,
            "rarity": badge.rarity,
            "message": _("Badge débloqué !"),
        }
