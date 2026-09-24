# -*- coding: utf-8 -*-
import os

from odoo import api, fields, models

_ENV_FALLBACK = {
    "doorway_elevenlabs_api_key": ("doorway_agents_dashboard.elevenlabs_api_key", "ELEVENLABS_API_KEY"),
    "doorway_twilio_account_sid": ("doorway_agents_dashboard.twilio_account_sid", "TWILIO_ACCOUNT_SID"),
    "doorway_twilio_auth_token": ("doorway_agents_dashboard.twilio_auth_token", "TWILIO_AUTH_TOKEN"),
    "doorway_twilio_phone_number": ("doorway_agents_dashboard.twilio_phone_number", "TWILIO_PHONE_NUMBER"),
    "doorway_anthropic_api_key": ("doorway_agents_dashboard.anthropic_api_key", "ANTHROPIC_API_KEY"),
    "doorway_vicidial_db_host": ("doorway_agents_dashboard.vicidial_db_host", "VICIDIAL_DB_HOST"),
    "doorway_vicidial_db_port": ("doorway_agents_dashboard.vicidial_db_port", "VICIDIAL_DB_PORT"),
    "doorway_vicidial_db_user": ("doorway_agents_dashboard.vicidial_db_user", "VICIDIAL_DB_USER"),
    "doorway_vicidial_db_password": (
        "doorway_agents_dashboard.vicidial_db_password",
        "VICIDIAL_DB_PASSWORD",
    ),
    "doorway_vicidial_db_name": ("doorway_agents_dashboard.vicidial_db_name", "VICIDIAL_DB_NAME"),
}


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doorway_elevenlabs_api_key = fields.Char(
        string="ElevenLabs API Key",
        config_parameter="doorway_agents_dashboard.elevenlabs_api_key",
    )
    doorway_twilio_account_sid = fields.Char(
        config_parameter="doorway_agents_dashboard.twilio_account_sid",
    )
    doorway_twilio_auth_token = fields.Char(
        config_parameter="doorway_agents_dashboard.twilio_auth_token",
    )
    doorway_twilio_phone_number = fields.Char(
        config_parameter="doorway_agents_dashboard.twilio_phone_number",
    )
    doorway_anthropic_api_key = fields.Char(
        config_parameter="doorway_agents_dashboard.anthropic_api_key",
    )
    doorway_vicidial_db_host = fields.Char(
        default="127.0.0.1",
        config_parameter="doorway_agents_dashboard.vicidial_db_host",
    )
    doorway_vicidial_db_port = fields.Char(
        default="3307",
        config_parameter="doorway_agents_dashboard.vicidial_db_port",
    )
    doorway_vicidial_db_user = fields.Char(
        config_parameter="doorway_agents_dashboard.vicidial_db_user",
    )
    doorway_vicidial_db_password = fields.Char(
        config_parameter="doorway_agents_dashboard.vicidial_db_password",
    )
    doorway_vicidial_db_name = fields.Char(
        default="asterisk",
        config_parameter="doorway_agents_dashboard.vicidial_db_name",
    )
    doorway_google_sheets_enabled = fields.Boolean(
        string="Activer export Google Sheets",
        config_parameter="doorway_agents_dashboard.google_sheets_enabled",
    )
    doorway_google_sheets_spreadsheet_id = fields.Char(
        string="Google Spreadsheet ID",
        config_parameter="doorway_agents_dashboard.google_sheets_spreadsheet_id",
    )
    doorway_google_sheets_sheet_name = fields.Char(
        string="Nom de l'onglet",
        default="Appels IA",
        config_parameter="doorway_agents_dashboard.google_sheets_sheet_name",
    )
    doorway_google_sheets_credentials_json = fields.Char(
        string="Credentials JSON (service account)",
        config_parameter="doorway_agents_dashboard.google_sheets_credentials_json",
    )
    doorway_google_sheets_webhook_url = fields.Char(
        string="Webhook Apps Script (optionnel)",
        config_parameter="doorway_agents_dashboard.google_sheets_webhook_url",
        help="Alternative simple : URL d'un Google Apps Script déployé en Web App.",
    )
    doorway_google_api_key = fields.Char(
        string="Google API Key (Sheets)",
        config_parameter="doorway_agents_dashboard.google_api_key",
        help="Clé API Google Cloud (Sheets API activée). Complément ou alternative au JSON service account.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env["ir.config_parameter"].sudo()
        for field_name, (param_key, env_key) in _ENV_FALLBACK.items():
            if not res.get(field_name):
                res[field_name] = icp.get_param(param_key) or os.environ.get(env_key) or ""
        return res
