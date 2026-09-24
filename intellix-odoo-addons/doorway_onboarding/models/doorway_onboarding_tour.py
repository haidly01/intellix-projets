# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayOnboardingTour(models.Model):
    _name = "doorway.onboarding.tour"
    _description = "Tour de visite guidée Doorway"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    quest_label = fields.Char(
        string="Libellé quête",
        default="Quête Doorway",
        translate=True,
    )
    home_action_xmlid = fields.Char(
        string="Action d'accueil (XML ID)",
        help="Action ouverte après la visite (ex. module.action_dashboard).",
    )
    home_action_method = fields.Char(
        string="Méthode d'accueil",
        help="Méthode @api.model sur doorway.onboarding.service (ex. home_people_engine).",
    )
    badge_icon = fields.Char(default="🚀")
    badge_name = fields.Char(translate=True)
    reward_points = fields.Integer(default=50)
    pe_badge_xmlid = fields.Char(
        string="Badge People Engine (XML ID)",
        help="Si People Engine est installé, attribue ce badge PE.",
    )
    step_ids = fields.One2many(
        "doorway.onboarding.tour.step", "tour_id", string="Étapes"
    )

    _doorway_tour_code_unique = models.Constraint(
        "UNIQUE(code)",
        "Le code du tour doit être unique.",
    )


class DoorwayOnboardingTourStep(models.Model):
    _name = "doorway.onboarding.tour.step"
    _description = "Étape de visite guidée"
    _order = "sequence, id"

    tour_id = fields.Many2one(
        "doorway.onboarding.tour", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    key = fields.Char(required=True, help="Identifiant technique de l'étape.")
    title = fields.Char(required=True, translate=True)
    body_html = fields.Html(sanitize_attributes=False, translate=True)
    admin_only = fields.Boolean(
        string="Administrateurs seulement",
        help="Visible seulement pour base.group_system.",
    )
    action_xmlid = fields.Char(string="Action lien (XML ID)")
    action_label = fields.Char(string="Libellé du bouton", translate=True)
