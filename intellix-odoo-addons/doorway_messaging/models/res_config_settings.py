# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    messaging_claude_api_key = fields.Char(
        string="Claude API Key (Messaging)",
        config_parameter="doorway_messaging.claude_api_key",
    )
    messaging_twilio_account_sid = fields.Char(
        config_parameter="doorway_messaging.twilio_account_sid",
    )
    messaging_twilio_auth_token = fields.Char(
        config_parameter="doorway_messaging.twilio_auth_token",
    )
    messaging_twilio_whatsapp_from = fields.Char(
        config_parameter="doorway_messaging.twilio_whatsapp_from",
    )
    messaging_twilio_sms_from = fields.Char(
        config_parameter="doorway_messaging.twilio_sms_from",
    )
    messaging_twilio_messaging_service_sid = fields.Char(
        string="Twilio Messaging Service SID (SMS, MG…)",
        config_parameter="doorway_messaging.twilio_messaging_service_sid",
    )
    messaging_twilio_whatsapp_messaging_service_sid = fields.Char(
        string="Twilio Messaging Service SID (WhatsApp, MG…)",
        config_parameter="doorway_messaging.twilio_whatsapp_messaging_service_sid",
    )
    messaging_linkedin_client_id = fields.Char(
        config_parameter="doorway_messaging.linkedin_client_id",
    )
    messaging_linkedin_client_secret = fields.Char(
        config_parameter="doorway_messaging.linkedin_client_secret",
    )
    messaging_google_client_id = fields.Char(
        config_parameter="doorway_messaging.google_client_id",
    )
    messaging_google_client_secret = fields.Char(
        config_parameter="doorway_messaging.google_client_secret",
    )
    messaging_n8n_wa_send_url = fields.Char(
        string="n8n wa-send URL",
        config_parameter="doorway_messaging.n8n_wa_send_url",
    )
    messaging_n8n_wa_bulk_url = fields.Char(
        string="n8n wa-bulk URL",
        config_parameter="doorway_messaging.n8n_wa_bulk_url",
    )
    messaging_n8n_wa_inbound_url = fields.Char(
        string="n8n wa-inbound URL (Twilio callback)",
        config_parameter="doorway_messaging.n8n_wa_inbound_url",
    )
