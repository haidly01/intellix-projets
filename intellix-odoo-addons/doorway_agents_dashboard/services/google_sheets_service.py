# -*- coding: utf-8 -*-
"""Export appels vers Google Sheets (API v4 ou webhook Apps Script)."""
import json
import logging
import time

import jwt
import requests

from odoo import _, fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SHEET_HEADERS = [
    "Date",
    "Agent",
    "Type appel",
    "De",
    "Vers",
    "Contact",
    "Email",
    "Téléphone contact",
    "Durée (sec)",
    "Score",
    "Transcription",
    "URL enregistrement",
    "ID appel",
    "Notes",
]

SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class GoogleSheetsService:
    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _enabled_globally(self):
        return self._icp.get_param(
            "doorway_agents_dashboard.google_sheets_enabled", "False"
        ) in ("True", "1", "true")

    def _webhook_url(self, agent=None):
        if agent and (agent.google_sheets_webhook_url or "").strip():
            return agent.google_sheets_webhook_url.strip()
        return (
            self._icp.get_param("doorway_agents_dashboard.google_sheets_webhook_url")
            or ""
        ).strip()

    def _spreadsheet_id(self, agent=None):
        if agent and (agent.google_sheets_spreadsheet_id or "").strip():
            return agent.google_sheets_spreadsheet_id.strip()
        return (
            self._icp.get_param("doorway_agents_dashboard.google_sheets_spreadsheet_id")
            or ""
        ).strip()

    def _sheet_name(self):
        return (
            self._icp.get_param("doorway_agents_dashboard.google_sheets_sheet_name")
            or "Appels IA"
        ).strip()

    def _api_key(self):
        return (
            self._icp.get_param("doorway_agents_dashboard.google_api_key") or ""
        ).strip()

    def _credentials(self):
        raw = self._icp.get_param(
            "doorway_agents_dashboard.google_sheets_credentials_json"
        ) or ""
        raw = raw.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            _logger.warning("Google Sheets credentials JSON invalide: %s", exc)
            return None

    def is_configured(self):
        return bool(
            self._webhook_url()
            or (self._spreadsheet_id() and self._credentials())
            or (self._spreadsheet_id() and self._api_key())
        )

    def should_export_agent(self, agent):
        if not agent:
            return False
        if not self._enabled_globally():
            return False
        if not agent.export_calls_google_sheet:
            return False
        return bool(self._webhook_url(agent) or self._spreadsheet_id(agent))

    def _access_token(self, credentials):
        now = int(time.time())
        payload = {
            "iss": credentials["client_email"],
            "scope": SCOPE,
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        assertion = jwt.encode(
            payload,
            credentials["private_key"],
            algorithm="RS256",
        )
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError(
                _("Token Google OAuth échoué (%s): %s")
                % (response.status_code, response.text[:300])
            )
        return response.json().get("access_token")

    def _append_via_api_key(self, row, agent=None):
        spreadsheet_id = self._spreadsheet_id(agent)
        api_key = self._api_key()
        if not spreadsheet_id or not api_key:
            return False
        sheet_name = self._sheet_name()
        range_name = "%s!A:A" % sheet_name
        url = (
            "https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s:append"
            % (spreadsheet_id, range_name)
        )
        response = requests.post(
            url,
            params={
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
                "key": api_key,
            },
            json={"values": [row]},
            timeout=25,
        )
        if response.status_code >= 400:
            raise UserError(
                _("Export Google Sheets (API key) échoué (%s): %s")
                % (response.status_code, response.text[:400])
            )
        return True

    def _append_via_api(self, row, agent=None):
        spreadsheet_id = self._spreadsheet_id(agent)
        credentials = self._credentials()
        if not spreadsheet_id or not credentials:
            return False
        token = self._access_token(credentials)
        sheet_name = self._sheet_name()
        range_name = "%s!A:A" % sheet_name
        url = (
            "https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s:append"
            % (spreadsheet_id, range_name)
        )
        response = requests.post(
            url,
            headers={
                "Authorization": "Bearer %s" % token,
                "Content-Type": "application/json",
            },
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": [row]},
            timeout=25,
        )
        if response.status_code >= 400:
            raise UserError(
                _("Export Google Sheets échoué (%s): %s")
                % (response.status_code, response.text[:400])
            )
        return True

    def _append_via_webhook(self, payload, agent=None):
        url = self._webhook_url(agent)
        if not url:
            return False
        response = requests.post(url, json=payload, timeout=25)
        if response.status_code >= 400:
            raise UserError(
                _("Webhook Google Sheets échoué (%s): %s")
                % (response.status_code, response.text[:300])
            )
        return True

    def _lead_contact(self, lead):
        if not lead:
            return "", "", ""
        name = lead.contact_name or lead.name or ""
        email = lead.email_from or ""
        phone = lead.phone or lead.mobile or ""
        return name, email, phone

    def _build_row(self, vals):
        return [
            vals.get("date") or "",
            vals.get("agent_name") or "",
            vals.get("call_type") or "",
            vals.get("from_number") or "",
            vals.get("to_number") or "",
            vals.get("contact_name") or "",
            vals.get("contact_email") or "",
            vals.get("contact_phone") or "",
            str(vals.get("duration") or 0),
            str(vals.get("score") or ""),
            (vals.get("transcript") or "")[:50000],
            vals.get("recording_url") or "",
            vals.get("external_call_id") or "",
            vals.get("notes") or "",
        ]

    def append_call(self, agent, payload):
        """Ajoute une ligne si l'export est activé pour cet agent."""
        if not self.should_export_agent(agent):
            return False
        row = self._build_row(payload)
        webhook_payload = dict(payload)
        webhook_payload["headers"] = SHEET_HEADERS
        webhook_payload["row"] = row
        try:
            if self._webhook_url(agent):
                return self._append_via_webhook(webhook_payload, agent=agent)
            if self._api_key() and self._spreadsheet_id(agent):
                return self._append_via_api_key(row, agent=agent)
            return self._append_via_api(row, agent=agent)
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Google Sheets append_call: %s", exc)
            return False

    def export_test_call(self, test_call, recording_url=None):
        test_call.ensure_one()
        agent = test_call.agent_id
        contact_name, contact_email, contact_phone = "", "", test_call.phone_number or ""
        return self.append_call(
            agent,
            {
                "date": fields.Datetime.to_string(test_call.create_date),
                "agent_name": agent.name,
                "call_type": "test",
                "from_number": "",
                "to_number": test_call.phone_number or "",
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "duration": test_call.duration_seconds,
                "score": test_call.score_global,
                "transcript": test_call.transcript or "",
                "recording_url": recording_url or test_call.recording_url or "",
                "external_call_id": test_call.external_call_id or "",
                "notes": test_call.analyse_ia or "",
            },
        )

    def export_call_session(self, session, recording_url=None):
        session.ensure_one()
        agent = session.agent_id
        lead = session.lead_id
        contact_name, contact_email, contact_phone = self._lead_contact(lead)
        return self.append_call(
            agent,
            {
                "date": fields.Datetime.to_string(session.date_start or session.create_date),
                "agent_name": agent.name if agent else "",
                "call_type": "production",
                "from_number": session.from_number or "",
                "to_number": session.to_number or "",
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "duration": session.duration,
                "score": session.report_id.score_global if session.report_id else "",
                "transcript": session.transcript or "",
                "recording_url": recording_url or session.recording_url or "",
                "external_call_id": session.twilio_call_sid or "",
                "notes": session.report_id.claude_summary if session.report_id else "",
            },
        )
