# -*- coding: utf-8 -*-
"""Setup ElevenLabs — Haidly (SoumissionEntrepreneurs)."""
import json
import logging
from pathlib import Path

import requests

from odoo import _
from odoo.exceptions import UserError

from .elevenlabs_client import BASE, ElevenLabsClient
from .elevenlabs_haidly import (
    AGENT_CONVAI_NAME,
    FROM_NUMBER,
    HAIDLY_FIRST_MESSAGE,
    HAIDLY_SYSTEM_PROMPT,
    SIP_TRUNK_SID,
    TRANSFER_NUMBER,
    VOICE_NAME,
)
from .elevenlabs_haidly_relance import RELANCE_HAIDLY_SPECS
from .elevenlabs_setup import ElevenLabsMaisonImmoSetup
from .elevenlabs_voicemail import inject_voicemail_detection

_logger = logging.getLogger(__name__)


class ElevenLabsHaidlySetup(ElevenLabsMaisonImmoSetup):

    def _existing_voice_id(self, agent_profile=None):
        vid = (
            self.icp.get_param("doorway_agents_dashboard.elevenlabs_voice_id_haidly")
            or self.icp.get_param("doorway_agents_dashboard.elevenlabs_voice_id_sophie")
            or ""
        ).strip()
        if vid:
            return vid
        if agent_profile and agent_profile.voice_clone_id:
            return agent_profile.voice_clone_id.strip()
        return ""

    def build_agent_payload(self, voice_id):
        payload = {
            "name": AGENT_CONVAI_NAME,
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": HAIDLY_SYSTEM_PROMPT,
                        "llm": "claude-3-5-sonnet",
                        "temperature": 0.55,
                        "max_tokens": 280,
                    },
                    "first_message": HAIDLY_FIRST_MESSAGE,
                    "language": "fr",
                },
                "tts": {
                    "voice_id": voice_id,
                    "model_id": "eleven_turbo_v2_5",
                    "optimize_streaming_latency": 4,
                    "stability": 0.42,
                    "similarity_boost": 0.82,
                    "style": 0.30,
                    "use_speaker_boost": True,
                },
                "asr": {"provider": "elevenlabs"},
                "turn": {"turn_timeout": 10, "silence_end_call_timeout": 40},
                "conversation": {"max_duration_seconds": 240},
            },
        }
        return inject_voicemail_detection(payload)

    def create_relance_agents(self, voice_id, update_existing=False):
        created = {}
        Profile = self.env["doorway.agent.profile"].sudo()
        for spec in RELANCE_HAIDLY_SPECS:
            payload = self.build_relance_payload(spec, voice_id)
            if "stability" in spec:
                payload["conversation_config"]["tts"]["stability"] = spec["stability"]
            existing = (self.icp.get_param(spec["icp_param"]) or "").strip()
            if existing and not existing.startswith("agent_"):
                existing = ""
            if existing and update_existing:
                response = requests.patch(
                    "%s/convai/agents/%s" % (BASE, existing),
                    headers=self.client.headers,
                    json=payload,
                    timeout=60,
                )
                if response.status_code >= 400:
                    raise UserError(
                        _("Échec MAJ relance %(key)s: %(err)s")
                        % {"key": spec["key"], "err": response.text[:400]}
                    )
                agent_id = existing
            else:
                response = requests.post(
                    "%s/convai/agents/create" % BASE,
                    headers=self.client.headers,
                    json=payload,
                    timeout=60,
                )
                if response.status_code >= 400:
                    minimal = {
                        "name": spec["odoo_name"],
                        "conversation_config": payload["conversation_config"],
                    }
                    response = requests.post(
                        "%s/convai/agents/create" % BASE,
                        headers=self.client.headers,
                        json=minimal,
                        timeout=60,
                    )
                if response.status_code >= 400:
                    raise UserError(
                        _("Échec création relance %(key)s: %(err)s")
                        % {"key": spec["key"], "err": response.text[:400]}
                    )
                agent_id = (response.json() or {}).get("agent_id") or ""
            self.icp.set_param(spec["icp_param"], agent_id)
            created[spec["key"]] = agent_id
            role = spec.get("haidly_role")
            odoo_agent = Profile.browse()
            if role:
                odoo_agent = Profile.search([("haidly_agent_role", "=", role)], limit=1)
            if not odoo_agent and spec.get("xmlid"):
                odoo_agent = self.env.ref(spec["xmlid"], raise_if_not_found=False)
            if odoo_agent:
                odoo_agent.write(
                    {
                        "name": spec["odoo_name"],
                        "haidly_agent_role": role,
                        "provider": "elevenlabs",
                        "external_agent_id": agent_id,
                        "voice_clone_id": voice_id,
                        "voice_name": VOICE_NAME,
                        "status": "active",
                        "agent_type": "outbound",
                        "pipeline": "renovation",
                        "system_prompt": spec["prompt"],
                    }
                )
        ids_path = (
            Path(__file__).resolve().parents[1]
            / "voice_samples"
            / "elevenlabs_haidly_ids.json"
        )
        try:
            data = {}
            if ids_path.is_file():
                data = json.loads(ids_path.read_text(encoding="utf-8"))
            data["relance_agents"] = created
            data["voice_id"] = data.get("voice_id") or voice_id
            ids_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            _logger.warning("elevenlabs_haidly_ids.json: %s", exc)
        return created

    def run_full_setup(self, agent_profile=None, update_existing=False):
        voice_id = self._existing_voice_id(agent_profile)
        if not voice_id:
            audio_bytes, filename = self._resolve_audio_bytes(agent_profile)
            voice_id = self.create_voice_clone(audio_bytes, filename)

        existing_id = (agent_profile.external_agent_id or "").strip() if agent_profile else ""
        placeholder = existing_id in ("", "ELEVENLABS_AGENT_ID_HAIDLY", "haidly")
        if existing_id and not placeholder and update_existing:
            agent_id = self.update_convai_agent(existing_id, voice_id)
        else:
            agent_id = self.create_convai_agent(voice_id)

        self.icp.set_param("doorway_agents_dashboard.elevenlabs_voice_id_haidly", voice_id)
        self.icp.set_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly", agent_id)

        if agent_profile:
            agent_profile.sudo().write(
                {
                    "name": "Haidly · J+0 Qualification",
                    "haidly_agent_role": "j0_qualification",
                    "provider": "elevenlabs",
                    "external_agent_id": agent_id,
                    "voice_clone_id": voice_id,
                    "voice_name": VOICE_NAME,
                    "transfer_phone": TRANSFER_NUMBER,
                    "default_volet": "qualification",
                    "agent_type": "outbound",
                    "pipeline": "renovation",
                    "timezone": "America/Toronto",
                    "status": "active",
                    "system_prompt": HAIDLY_SYSTEM_PROMPT,
                }
            )
            for phone in agent_profile.phone_number_ids:
                phone.write(
                    {
                        "twilio_sip_trunk_sid": SIP_TRUNK_SID,
                        "phone_number": FROM_NUMBER,
                        "sip_trunk_name": "Haidly-5817058118",
                    }
                )
            try:
                ph_id = self.client.ensure_twilio_phone_number(
                    FROM_NUMBER,
                    agent_id=agent_id,
                    label=AGENT_CONVAI_NAME,
                )
                self.icp.set_param(
                    "doorway_agents_dashboard.elevenlabs_phone_number_id_haidly",
                    ph_id,
                )
                agent_profile.phone_number_ids.write(
                    {"elevenlabs_phone_number_id": ph_id}
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Import numéro Twilio Haidly: %s", exc)

        relance_ids = {}
        try:
            relance_ids = self.create_relance_agents(voice_id, update_existing=update_existing)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Agents relance Haidly: %s", exc)

        return {
            "voice_id": voice_id,
            "agent_id": agent_id,
            "relance_agents": relance_ids,
            "from_number": FROM_NUMBER,
            "sip_trunk_sid": SIP_TRUNK_SID,
            "transfer_number": TRANSFER_NUMBER,
        }

    def run_relance_setup(self, agent_profile=None, update_existing=False):
        voice_id = self._existing_voice_id(agent_profile)
        if not voice_id:
            raise UserError(_("Voice ID manquant. Lancez « Setup ElevenLabs (Haidly) »."))
        return self.create_relance_agents(voice_id, update_existing=update_existing)
