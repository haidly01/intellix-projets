# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwaySocialLinkedinProfile(models.Model):
    _name = "doorway.social.linkedin.profile"
    _description = "Profil LinkedIn (personnel ou entreprise)"
    _order = "profile_type, name"

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        "doorway.social.account",
        required=True,
        ondelete="cascade",
        domain=[("platform", "=", "linkedin")],
    )
    channel_config_id = fields.Many2one(
        "doorway.channel.config",
        string="Canal OAuth",
        ondelete="set null",
        domain=[("canal", "=", "linkedin")],
    )
    profile_type = fields.Selection(
        [
            ("personal", "Profil personnel"),
            ("organization", "Page entreprise"),
        ],
        required=True,
        default="organization",
    )
    external_urn = fields.Char(
        "URN LinkedIn",
        help="urn:li:person:XXX ou urn:li:organization:XXX",
    )
    external_id = fields.Char(
        "ID numérique",
        compute="_compute_external_id",
        store=True,
    )
    active = fields.Boolean(default=True)

    @api.depends("external_urn")
    def _compute_external_id(self):
        for rec in self:
            urn = (rec.external_urn or "").strip()
            rec.external_id = urn.split(":")[-1] if urn else ""

    def _linkedin_service(self):
        self.ensure_one()
        cfg = self.channel_config_id
        if not cfg or not cfg.access_token:
            return None
        from odoo.addons.doorway_messaging.services.linkedin_service import (
            LinkedInService,
        )

        org_id = ""
        person_id = ""
        if self.profile_type == "organization":
            org_id = self.external_id or (cfg.linkedin_org_id or "").replace(
                "urn:li:organization:", ""
            )
        else:
            person_id = self.external_id or (cfg.linkedin_person_id or "").replace(
                "urn:li:person:", ""
            )
        return LinkedInService(cfg.access_token, org_id=org_id, person_id=person_id)
