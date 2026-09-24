# -*- coding: utf-8 -*-
"""Client API Retell — agents, appels, transcriptions."""
import logging

import requests

from odoo import fields

from .config_loader import get_secret

_logger = logging.getLogger(__name__)

BASE = "https://api.retellai.com"


class RetellClient:
    def __init__(self, env=None):
        self.env = env
        api_key = get_secret(
            env,
            "RETELL_API_KEY",
            "doorway_agents_dashboard.retell_api_key",
            ["renovation_conciergerie.retell_api_key"],
        )
        self.headers = {
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        }

    def list_agents(self):
        r = requests.get(
            "%s/list-agents" % BASE,
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def sync_agent(self, agent_profile_record):
        agent_profile_record.ensure_one()
        try:
            r = requests.get(
                "%s/get-agent/%s" % (BASE, agent_profile_record.external_agent_id),
                headers=self.headers,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                agent_profile_record.write(
                    {
                        "status": "active",
                        "voice_name": data.get("voice_id", ""),
                        "last_sync": fields.Datetime.now(),
                    }
                )
            else:
                agent_profile_record.write({"status": "error"})
        except requests.RequestException as exc:
            _logger.warning("Retell sync_agent: %s", exc)
            agent_profile_record.write({"status": "error"})

    def start_phone_call(self, agent_id, to_number, from_number, metadata=None):
        payload = {
            "from_number": from_number,
            "to_number": to_number,
            "agent_id": agent_id,
            "metadata": metadata or {"test_call": True},
        }
        r = requests.post(
            "%s/create-phone-call" % BASE,
            json=payload,
            headers=self.headers,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def get_call(self, call_id):
        r = requests.get(
            "%s/get-call/%s" % (BASE, call_id),
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # --- Adaptateurs Odoo ---

    def is_available(self):
        auth = self.headers.get("Authorization") or ""
        return bool(auth.replace("Bearer", "").strip())

    def _from_number(self):
        return get_secret(
            self.env,
            "TWILIO_FROM_NUMBER",
            "doorway_agents_dashboard.retell_from_number",
            ["renovation_conciergerie.retell_from_number"],
        )

    def _normalize_agents(self, data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("agents") or []
        return []

    def sync_profiles(self):
        if not self.is_available():
            return 0
        try:
            agents = self._normalize_agents(self.list_agents())
        except requests.RequestException as exc:
            _logger.warning("Retell sync_profiles: %s", exc)
            return 0
        Profile = self.env["doorway.agent.profile"].sudo()
        count = 0
        seen = set()
        for item in agents:
            agent_id = item.get("agent_id") or item.get("id")
            if not agent_id or agent_id in seen:
                continue
            seen.add(agent_id)
            name = item.get("agent_name") or item.get("name") or agent_id
            api_lang = item.get("language") or ""
            published = item.get("is_published")
            vals = {
                "name": name,
                "provider": "retell",
                "external_agent_id": agent_id,
                "pipeline": Profile._infer_pipeline(name),
                "agent_type": Profile._infer_agent_type(name),
                "language": Profile._infer_language(name, api_lang),
                "voice_name": item.get("voice_id") or "",
                "description": item.get("description") or False,
                "status": "active" if published is not False else "inactive",
                "last_sync": fields.Datetime.now(),
            }
            existing = Profile.search(
                [
                    ("provider", "=", "retell"),
                    ("external_agent_id", "=", agent_id),
                ],
                limit=1,
            )
            if existing:
                existing.write(vals)
            else:
                Profile.create(vals)
            count += 1
        return count

    def start_test_call(self, test_call):
        test_call.ensure_one()
        if not self.is_available():
            return {"ok": False, "message": "Clé Retell absente."}
        from_number = self._from_number()
        if not from_number:
            return {
                "ok": False,
                "message": "Numéro émetteur Retell manquant (paramètres Odoo).",
            }
        to_number = (test_call.phone_number or "").strip()
        if not to_number:
            return {"ok": False, "message": "Numéro de téléphone requis."}
        metadata = {
            "test_call": True,
            "test_call_id": test_call.id,
            "source": "doorway_agents_dashboard",
        }
        try:
            body = self.start_phone_call(
                test_call.agent_id.external_agent_id,
                to_number,
                from_number,
                metadata=metadata,
            )
            ext_id = body.get("call_id") or body.get("id")
            return {
                "ok": True,
                "external_call_id": ext_id,
                "state": "in_progress",
                "raw": body,
            }
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def fetch_call(self, call_id):
        """Alias compat webhook — ne lève pas si échec."""
        if not call_id or not self.is_available():
            return {}
        try:
            return self.get_call(call_id)
        except requests.RequestException as exc:
            _logger.warning("Retell get_call %s: %s", call_id, exc)
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
        return call_data.get("transcript_object") or ""
