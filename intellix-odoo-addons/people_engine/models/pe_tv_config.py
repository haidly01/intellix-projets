# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models


class PeopleEngineTVConfig(models.Model):
    _name = "pe.tv.config"
    _description = "Configuration dashboard TV People Engine"

    name = fields.Char(required=True)
    department_id = fields.Many2one("hr.department")
    show_leaderboard = fields.Boolean(default=True)
    show_badges_feed = fields.Boolean(default=True)
    show_challenges = fields.Boolean(default=True)
    show_team_score = fields.Boolean(default=True)
    show_top_performers = fields.Boolean(default=True)
    show_course_completions = fields.Boolean(default=True)
    slide_duration = fields.Integer(default=10)
    refresh_interval = fields.Integer(
        default=300,
        help="Actualisation des données (secondes)",
    )
    background_color = fields.Char(default="#0A0A0F")
    accent_color = fields.Char(default="#4F6EF7")
    public_token = fields.Char(
        default=lambda self: self._generate_token(),
        copy=False,
        required=True,
    )
    public_url = fields.Char(compute="_compute_public_url")
    active = fields.Boolean(default=True)

    _token_unique = models.Constraint(
        "unique(public_token)",
        "Le token TV doit être unique.",
    )

    @api.model
    def _generate_token(self):
        return secrets.token_urlsafe(32)

    @api.depends("public_token")
    def _compute_public_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        for config in self:
            if config.public_token:
                config.public_url = "%s/people-engine/tv/%s" % (
                    base.rstrip("/"),
                    config.public_token,
                )
            else:
                config.public_url = False

    def action_regenerate_token(self):
        for config in self:
            config.public_token = self._generate_token()

    @api.model
    def _cron_rotate_tokens(self):
        """Rotation des tokens tous les 90 jours (sécurité)."""
        configs = self.search([("active", "=", True)])
        for config in configs:
            config.action_regenerate_token()
