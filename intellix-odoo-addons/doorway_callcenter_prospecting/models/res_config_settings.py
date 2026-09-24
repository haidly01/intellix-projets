# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    callcenter_webhook_token = fields.Char(
        string="Token webhook prospection CC",
        config_parameter="doorway_callcenter_prospecting.webhook_token",
    )
    callcenter_demo_booking_url = fields.Char(
        string="URL réservation démo",
        config_parameter="doorway_callcenter_prospecting.demo_booking_url",
    )
    callcenter_agent_name = fields.Char(
        string="Nom agent campagne",
        config_parameter="doorway_callcenter_prospecting.agent_name",
        default="Karine",
    )
