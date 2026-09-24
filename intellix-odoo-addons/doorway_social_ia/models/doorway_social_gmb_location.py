# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySocialGmbLocation(models.Model):
    _name = "doorway.social.gmb.location"
    _description = "Établissement Google My Business"
    _order = "name"

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        "doorway.social.account",
        required=True,
        ondelete="cascade",
        domain=[("platform", "=", "gmb")],
    )
    channel_config_id = fields.Many2one(
        "doorway.channel.config",
        string="Canal OAuth",
        ondelete="set null",
        domain=[("canal", "=", "gmb")],
    )
    gmb_account_id = fields.Char("Account ID GMB")
    gmb_location_id = fields.Char("Location ID GMB")
    active = fields.Boolean(default=True)

    def _gmb_service(self):
        self.ensure_one()
        cfg = self.channel_config_id
        if not cfg or not cfg.access_token:
            return None
        from odoo.addons.doorway_messaging.services.gmb_service import GMBService

        return GMBService(
            cfg.access_token,
            self.gmb_account_id or cfg.gmb_account_id or "",
            self.gmb_location_id or cfg.gmb_location_id or "",
        )
