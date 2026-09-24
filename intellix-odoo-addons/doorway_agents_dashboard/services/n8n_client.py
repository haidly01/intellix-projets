# -*- coding: utf-8 -*-
"""Client n8n pour orchestrer agents ElevenLabs + Twilio."""
import logging

import requests

from odoo import fields

from .config_loader import get_secret

_logger = logging.getLogger(__name__)


class N8NClient:
    def __init__(self, env=None):
        self.env = env
        self.base_url = get_secret(
            env,
            "N8N_BASE_URL",
            "doorway_agents_dashboard.n8n_base_url",
        ).rstrip("/")
        self.token = get_secret(
            env,
            "N8N_API_TOKEN",
            "doorway_agents_dashboard.n8n_api_token",
        )
        self.agent_sync_path = get_secret(
            env,
            "N8N_AGENT_SYNC_PATH",
            "doorway_agents_dashboard.n8n_agent_sync_path",
        ) or "/webhook/doorway/agents/sync"
        self.start_call_path = get_secret(
            env,
            "N8N_START_CALL_PATH",
            "doorway_agents_dashboard.n8n_start_call_path",
        ) or "/webhook/doorway/agents/start-call"
        self.get_call_path = get_secret(
            env,
            "N8N_GET_CALL_PATH",
            "doorway_agents_dashboard.n8n_get_call_path",
        ) or "/webhook/doorway/agents/get-call"
        self.start_web_test_path = get_secret(
            env,
            "N8N_START_WEB_TEST_PATH",
            "doorway_agents_dashboard.n8n_start_web_test_path",
        ) or "/webhook/doorway/agents/start-web-test"

    def is_available(self):
        return bool(self.base_url and self.token)

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % self.token,
        }

    def _url(self, path):
        return "%s%s" % (self.base_url, path if path.startswith("/") else "/" + path)

    def list_agents(self):
        r = requests.post(
            self._url(self.agent_sync_path),
            json={"source": "odoo"},
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict):
            return body.get("agents") or []
        return body if isinstance(body, list) else []

    def sync_agent(self, agent_profile_record):
        agent_profile_record.ensure_one()
        if not self.is_available():
            agent_profile_record.write({"status": "error"})
            return
        try:
            r = requests.post(
                self._url(self.agent_sync_path),
                json={
                    "source": "odoo",
                    "agent_id": agent_profile_record.external_agent_id,
                },
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json() if r.content else {}
            agent = data.get("agent") if isinstance(data, dict) else {}
            agent_profile_record.write(
                {
                    "status": "active",
                    "voice_name": (agent or {}).get("voice_name") or agent_profile_record.voice_name,
                    "last_sync": fields.Datetime.now(),
                }
            )
        except requests.RequestException as exc:
            _logger.warning("n8n sync_agent: %s", exc)
            agent_profile_record.write({"status": "error"})

    def sync_profiles(self):
        if not self.is_available():
            return 0
        try:
            agents = self.list_agents()
        except requests.RequestException as exc:
            _logger.warning("n8n sync_profiles: %s", exc)
            return 0
        Profile = self.env["doorway.agent.profile"].sudo()
        count = 0
        seen = set()
        for item in agents:
            agent_id = item.get("agent_id") or item.get("id")
            if not agent_id or agent_id in seen:
                continue
            seen.add(agent_id)
            name = item.get("name") or item.get("agent_name") or agent_id
            api_lang = item.get("language") or ""
            vals = {
                "name": name,
                "provider": "n8n",
                "external_agent_id": agent_id,
                "pipeline": Profile._infer_pipeline(name),
                "agent_type": Profile._infer_agent_type(name),
                "language": Profile._infer_language(name, api_lang),
                "voice_name": item.get("voice_name") or item.get("voice_id") or "",
                "description": item.get("description") or False,
                "status": "active" if item.get("active", True) else "inactive",
                "last_sync": fields.Datetime.now(),
            }
            existing = Profile.search(
                [("provider", "=", "n8n"), ("external_agent_id", "=", agent_id)],
                limit=1,
            )
            if existing:
                existing.write(vals)
            else:
                Profile.create(vals)
            count += 1
        return count

    def start_web_test(self, test_call):
        """Prépare un test navigateur via n8n (Deepgram + Claude + ElevenLabs)."""
        test_call.ensure_one()
        if not self.is_available():
            return {"ok": False, "message": "Configuration n8n absente."}
        agent = test_call.agent_id
        volet = getattr(test_call, "call_volet", None) or agent.default_volet
        volet = agent._resolve_volet(volet)
        payload = {
            "source": "odoo",
            "mode": "browser_mic",
            "stack": "n8n+deepgram+claude+elevenlabs",
            "agent_id": agent.external_agent_id,
            "agent_profile_id": agent.id,
            "pipeline": agent.pipeline,
            "volet": volet,
            "scenario_hint": test_call.scenario_hint or "",
            "system_prompt": test_call._get_effective_script_prompt(),
            "first_message": test_call._resolve_web_test_first_message(),
            "test_call_id": test_call.id,
            "dynamic_variables": test_call._elevenlabs_dynamic_variables()
            if hasattr(test_call, "_elevenlabs_dynamic_variables")
            else {},
            "actions": {
                "send_email": bool(test_call.test_send_email),
                "send_sms": bool(test_call.test_send_sms),
                "availability_check": bool(test_call.test_availability_check),
                "human_transfer": bool(test_call.test_human_transfer),
            },
            "expected_action_result": test_call.expected_action_result or "",
        }
        try:
            r = requests.post(
                self._url(self.start_web_test_path),
                json=payload,
                headers=self._headers(),
                timeout=25,
            )
            r.raise_for_status()
            body = r.json() if r.content else {}
            return {
                "ok": True,
                "stack": "n8n",
                "conversation_token": body.get("conversation_token") or "",
                "signed_url": body.get("signed_url") or "",
                "websocket_url": body.get("websocket_url") or "",
                "session_url": body.get("session_url") or "",
                "external_call_id": (
                    body.get("call_id")
                    or body.get("conversation_id")
                    or body.get("session_id")
                    or body.get("id")
                    or ""
                ),
                "raw": body,
            }
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def start_test_call(self, test_call):
        test_call.ensure_one()
        if not self.is_available():
            return {"ok": False, "message": "Configuration n8n absente."}
        to_number = (test_call.phone_number or "").strip()
        if not to_number:
            return {"ok": False, "message": "Numéro de téléphone requis."}
        agent = test_call.agent_id
        phone_line = agent.default_phone_number_id
        volet = getattr(test_call, "call_volet", None) or agent.default_volet
        volet = agent._resolve_volet(volet)
        payload = {
            "source": "odoo",
            "agent_id": agent.external_agent_id,
            "agent_profile_id": agent.id,
            "pipeline": agent.pipeline,
            "volet": volet,
            "to_number": to_number,
            "from_number": (
                phone_line.phone_number
                if phone_line
                else get_secret(
                    self.env,
                    "TWILIO_FROM_NUMBER",
                    "doorway_agents_dashboard.elevenlabs_from_number",
                )
            ),
            "sip_trunk_name": phone_line.sip_trunk_name if phone_line else "",
            "sip_trunk_sid": phone_line.twilio_sip_trunk_sid if phone_line else "",
            "transfer_number": agent.transfer_phone or "+14389929200",
            "scenario_hint": test_call.scenario_hint or "",
            "test_call_id": test_call.id,
            "actions": {
                "send_email": bool(test_call.test_send_email),
                "send_sms": bool(test_call.test_send_sms),
                "availability_check": bool(test_call.test_availability_check),
                "human_transfer": bool(test_call.test_human_transfer),
            },
            "expected_action_result": test_call.expected_action_result or "",
        }
        try:
            r = requests.post(
                self._url(self.start_call_path),
                json=payload,
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            body = r.json() if r.content else {}
            ext_id = body.get("call_id") or body.get("conversation_id") or body.get("id")
            return {
                "ok": True,
                "external_call_id": ext_id,
                "state": "in_progress",
                "raw": body,
            }
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def fetch_call(self, call_id):
        if not call_id or not self.is_available():
            return {}
        try:
            r = requests.post(
                self._url(self.get_call_path),
                json={"source": "odoo", "call_id": call_id},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json() if r.content else {}
        except requests.RequestException as exc:
            _logger.warning("n8n get_call %s: %s", call_id, exc)
            return {}

    @staticmethod
    def extract_transcript(call_data):
        if not call_data:
            return ""
        transcript = call_data.get("transcript")
        if isinstance(transcript, str):
            return transcript
        if isinstance(transcript, list):
            lines = []
            for turn in transcript:
                role = turn.get("role") or "?"
                text = turn.get("content") or turn.get("text") or ""
                lines.append("%s: %s" % (role, text))
            return "\n".join(lines)
        return call_data.get("transcription") or ""
