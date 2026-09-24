# -*- coding: utf-8 -*-
"""Setup voix + agent ElevenLabs pour Maison Recherchée."""
import json
import logging
import os
from pathlib import Path

import requests

from odoo import _
from odoo.exceptions import UserError

from .config_loader import get_secret
from .elevenlabs_client import BASE, ElevenLabsClient
from .elevenlabs_voicemail import inject_voicemail_detection
from .elevenlabs_maison_immo import (
    AGENT_CONVAI_NAME,
    FROM_NUMBER,
    MIME_BY_EXT,
    SOPHIE_FIRST_MESSAGE,
    SOPHIE_SYSTEM_PROMPT,
    SIP_TRUNK_SID,
    TRANSFER_NUMBER,
    VOICE_CLONE_NAME,
)
from .elevenlabs_maison_immo_relance import RELANCE_AGENT_SPECS

_logger = logging.getLogger(__name__)


class ElevenLabsMaisonImmoSetup:
    def __init__(self, env):
        self.env = env
        self.client = ElevenLabsClient(env)
        self.icp = env["ir.config_parameter"].sudo()

    def _api_key(self):
        key = self.client.headers.get("xi-api-key") or ""
        if not key:
            raise UserError(_("Clé ElevenLabs absente (Paramètres ou ELEVENLABS_API_KEY)."))
        return key

    def _default_voice_path(self):
        custom = self.icp.get_param("doorway_agents_dashboard.maison_immo_voice_path")
        if custom and os.path.isfile(custom):
            return custom
        module_path = Path(__file__).resolve().parents[1] / "voice_samples" / "Rue_Ibnou_Jahir_3.m4a"
        return str(module_path)

    def _audio_from_agent_profile(self, agent_profile):
        """Lit l'échantillon voix (champ binaire ou pièce jointe ir.attachment)."""
        import base64

        agent_profile.ensure_one()
        if agent_profile.voice_sample_file:
            return (
                base64.b64decode(agent_profile.voice_sample_file),
                agent_profile.voice_sample_filename or "voice_sample.m4a",
            )
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "doorway.agent.profile"),
                    ("res_id", "=", agent_profile.id),
                    ("res_field", "=", "voice_sample_file"),
                ],
                order="id desc",
                limit=1,
            )
        )
        if attachment and attachment.datas:
            return (
                base64.b64decode(attachment.datas),
                agent_profile.voice_sample_filename
                or attachment.name
                or "voice_sample.m4a",
            )
        return None, None

    def _resolve_audio_bytes(self, agent_profile=None):
        if agent_profile:
            audio_bytes, filename = self._audio_from_agent_profile(agent_profile)
            if audio_bytes:
                return audio_bytes, filename
        path = self._default_voice_path()
        if os.path.isfile(path):
            filename = os.path.basename(path)
            with open(path, "rb") as handle:
                return handle.read(), filename
        if agent_profile:
            raise UserError(
                _(
                    "Aucun fichier audio sur l'agent « %(name)s ».\n\n"
                    "1. Onglet « Échantillon voix » : joignez Rue_Ibnou_Jahir_3.m4a (ou autre)\n"
                    "2. Cliquez sur Enregistrer (disquette) — obligatoire avant Setup\n"
                    "3. Relancez « Setup ElevenLabs (Sophie) »\n\n"
                    "Ou copiez le fichier sur le serveur :\n%(path)s"
                )
                % {"name": agent_profile.name, "path": path}
            )
        raise UserError(
            _(
                "Fichier voix introuvable: %(path)s\n"
                "Joignez l'audio sur la fiche Maison Recherchée puis Enregistrer."
            )
            % {"path": path}
        )

    def _raise_voice_clone_error(self, status_code, response_text):
        """Message lisible (plan EL, clé API, contournement voice_id existant)."""
        _logger.error("ElevenLabs voice add: %s", response_text)
        detail = {}
        try:
            detail = (json.loads(response_text).get("detail") or {}) if response_text else {}
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        code = detail.get("code") or detail.get("status") or ""
        if code in ("paid_plan_required", "can_not_use_instant_voice_cloning"):
            raise UserError(
                _(
                    "Votre abonnement ElevenLabs n'inclut pas le clonage vocal instantané "
                    "(API /v1/voices/add).\n\n"
                    "Options :\n"
                    "• Passer à un forfait Creator (ou supérieur) avec « Instant Voice Cloning » "
                    "sur https://elevenlabs.io/subscription\n"
                    "• Ou contourner le clone : dans la console ElevenLabs, choisissez une voix "
                    "française (bibliothèque ou clone déjà créé), copiez son voice_id, collez-le "
                    "dans le champ « Voice Clone ID » sur la fiche Maison Recherchée, Enregistrer, "
                    "puis relancez Setup (l'audio joint sera ignoré).\n\n"
                    "Paramètre serveur optionnel : "
                    "doorway_agents_dashboard.maison_immo_voice_id"
                )
            )
        raise UserError(
            _("Échec création voix ElevenLabs (%s): %s")
            % (status_code, response_text[:500])
        )

    def _existing_voice_id(self, agent_profile=None):
        """Voice ID déjà connu (fiche agent ou paramètre système) — évite /voices/add."""
        if agent_profile:
            vid = (agent_profile.voice_clone_id or "").strip()
            if vid and len(vid) > 8:
                return vid
        for key in (
            "doorway_agents_dashboard.maison_immo_voice_id",
            "doorway_agents_dashboard.elevenlabs_voice_id_sophie",
        ):
            vid = (self.icp.get_param(key) or "").strip()
            if vid and len(vid) > 8:
                return vid
        return ""

    def create_voice_clone(self, audio_bytes, filename):
        ext = os.path.splitext(filename)[1].lower()
        mime = MIME_BY_EXT.get(ext, "application/octet-stream")
        headers = {"xi-api-key": self._api_key()}
        labels = json.dumps(
            {
                "use_case": "conversational",
                "accent": "canadian_french",
                "gender": "female",
                "project": "doorway_immo",
            }
        )
        data = {
            "name": VOICE_CLONE_NAME,
            "description": (
                "Voix agent IA qualification immobilière Maison Recherchée / Agence Doorway. "
                "Français québécois, ton chaleureux et professionnel."
            ),
            "labels": labels,
        }
        files = [("files", (filename, audio_bytes, mime))]
        response = requests.post(
            "%s/voices/add" % BASE,
            headers=headers,
            data=data,
            files=files,
            timeout=120,
        )
        if response.status_code >= 400:
            self._raise_voice_clone_error(response.status_code, response.text)
        body = response.json()
        return body.get("voice_id") or ""

    def _n8n_postcall_url(self):
        return (
            self.icp.get_param("doorway_agents_dashboard.maison_immo_n8n_postcall_url")
            or "https://n8n.intellixcrm.com/webhook/elevenlabs-immo-postcall"
        )

    def _webhook_secret(self):
        return get_secret(
            self.env,
            "WEBHOOK_SECRET",
            "doorway_agents_dashboard.maison_immo_n8n_webhook_secret",
            ["renovation_conciergerie.meta_immo_webhook_token"],
        )

    def build_agent_payload(self, voice_id):
        payload = {
            "name": AGENT_CONVAI_NAME,
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": SOPHIE_SYSTEM_PROMPT,
                        "llm": "claude-3-5-sonnet",
                        "temperature": 0.4,
                        "max_tokens": 300,
                    },
                    "first_message": SOPHIE_FIRST_MESSAGE,
                    "language": "fr",
                },
                "tts": {
                    "voice_id": voice_id,
                    "model_id": "eleven_turbo_v2_5",
                    "optimize_streaming_latency": 4,
                    "stability": 0.5,
                    "similarity_boost": 0.85,
                    "style": 0.2,
                    "use_speaker_boost": True,
                },
                "asr": {
                    "provider": "elevenlabs",
                },
                "turn": {
                    "turn_timeout": 8,
                    "silence_end_call_timeout": 20,
                },
                "conversation": {
                    "max_duration_seconds": 480,
                },
            },
            "platform_settings": {
                "overrides": {
                    "conversation_config_override": {
                        "tts": {"voice_id": voice_id},
                    }
                },
            },
        }
        return inject_voicemail_detection(payload)

    def create_convai_agent(self, voice_id):
        payload = self.build_agent_payload(voice_id)
        response = requests.post(
            "%s/convai/agents/create" % BASE,
            headers=self.client.headers,
            json=payload,
            timeout=60,
        )
        if response.status_code >= 400:
            _logger.warning(
                "Agent create full payload failed (%s), retry minimal",
                response.status_code,
            )
            minimal = {
                "name": AGENT_CONVAI_NAME,
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
                _("Échec création agent ElevenLabs (%s): %s")
                % (response.status_code, response.text[:800])
            )
        body = response.json()
        return body.get("agent_id") or body.get("id") or ""

    def update_convai_agent(self, agent_id, voice_id):
        payload = self.build_agent_payload(voice_id)
        response = requests.patch(
            "%s/convai/agents/%s" % (BASE, agent_id),
            headers=self.client.headers,
            json=payload,
            timeout=60,
        )
        if response.status_code >= 400:
            raise UserError(
                _("Échec mise à jour agent (%s): %s")
                % (response.status_code, response.text[:800])
            )
        return agent_id

    def test_voice_tts(self, voice_id, output_path=None):
        output_path = output_path or (
            Path(__file__).resolve().parents[1] / "voice_samples" / "test_sophie_voice.mp3"
        )
        url = "%s/text-to-speech/%s" % (BASE, voice_id)
        data = {
            "text": SOPHIE_FIRST_MESSAGE,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.85,
                "style": 0.2,
                "use_speaker_boost": True,
            },
        }
        response = requests.post(
            url,
            headers=self.client.headers,
            json=data,
            timeout=60,
        )
        if response.status_code >= 400:
            raise UserError(_("Test TTS échoué: %s") % response.text[:300])
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as handle:
            handle.write(response.content)
        return str(output_path)

    def build_relance_payload(self, spec, voice_id):
        payload = {
            "name": spec["odoo_name"],
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": spec["prompt"],
                        "llm": "claude-3-5-sonnet",
                        "temperature": spec.get("temperature", 0.35),
                        "max_tokens": spec.get("max_tokens", 200),
                    },
                    "first_message": spec["first_message"],
                    "language": "fr",
                },
                "tts": {
                    "voice_id": voice_id,
                    "model_id": "eleven_turbo_v2_5",
                    "optimize_streaming_latency": 4,
                    "stability": spec.get("stability", 0.5),
                    "similarity_boost": 0.85,
                },
                "asr": {"provider": "elevenlabs"},
                "turn": {
                    "turn_timeout": spec.get("turn_timeout", 8),
                    "silence_end_call_timeout": spec.get(
                        "silence_end_call_timeout", 18
                    ),
                },
                "conversation": {
                    "max_duration_seconds": spec.get("max_duration_seconds", 240),
                },
            },
        }
        return inject_voicemail_detection(payload)

    def create_relance_agents(self, voice_id, update_existing=False):
        """Crée ou met à jour les 4 agents ConvAI de relance (même voix Sophie)."""
        created = {}
        Profile = self.env["doorway.agent.profile"].sudo()
        for spec in RELANCE_AGENT_SPECS:
            payload = self.build_relance_payload(spec, voice_id)
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
            odoo_agent = Profile.browse()
            if spec.get("immo_role"):
                odoo_agent = Profile.search(
                    [("immo_agent_role", "=", spec["immo_role"])],
                    limit=1,
                )
            if not odoo_agent and spec.get("xmlid"):
                odoo_agent = self.env.ref(spec["xmlid"], raise_if_not_found=False)
            if not odoo_agent:
                odoo_agent = Profile.search(
                    [("name", "=", spec["odoo_name"])],
                    limit=1,
                )
            if odoo_agent:
                odoo_agent.write(
                    {
                        "name": spec["odoo_name"],
                        "immo_agent_role": spec.get("immo_role"),
                        "provider": "elevenlabs",
                        "external_agent_id": agent_id,
                        "voice_clone_id": voice_id,
                        "voice_name": VOICE_CLONE_NAME,
                        "status": "active",
                        "agent_type": "outbound",
                        "pipeline": "immobilier",
                        "system_prompt": spec["prompt"],
                    }
                )
        ids_path = (
            Path(__file__).resolve().parents[1] / "voice_samples" / "elevenlabs_ids.json"
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
            _logger.warning("elevenlabs_ids.json: %s", exc)
        return created

    def run_relance_setup(self, agent_profile=None, update_existing=False):
        """Crée les 4 agents de relance (voice_id existant requis)."""
        voice_id = self._existing_voice_id(agent_profile)
        if not voice_id:
            voice_id = (self.icp.get_param("doorway_agents_dashboard.elevenlabs_voice_id_sophie") or "").strip()
        if not voice_id:
            raise UserError(
                _(
                    "Voice ID Sophie manquant. Lancez d'abord "
                    "« Setup ElevenLabs (Sophie) » sur Maison Recherchée."
                )
            )
        return self.create_relance_agents(voice_id, update_existing=update_existing)

    def run_full_setup(self, agent_profile=None, update_existing=False):
        """Crée voix + agent EL et met à jour le profil Odoo Maison Recherchée."""
        voice_id = self._existing_voice_id(agent_profile)
        if voice_id:
            _logger.info(
                "Setup Sophie: voice_id existant %s (pas de clonage API)",
                voice_id[:12],
            )
        else:
            audio_bytes, filename = self._resolve_audio_bytes(agent_profile)
            voice_id = self.create_voice_clone(audio_bytes, filename)

        existing_id = (agent_profile.external_agent_id or "").strip() if agent_profile else ""
        placeholder = existing_id in ("", "ELEVENLABS_AGENT_ID_IMMO", "maison_recherchee")
        if existing_id and not placeholder and update_existing:
            agent_id = self.update_convai_agent(existing_id, voice_id)
        else:
            agent_id = self.create_convai_agent(voice_id)

        self.icp.set_param("doorway_agents_dashboard.elevenlabs_voice_id_sophie", voice_id)
        self.icp.set_param("doorway_agents_dashboard.elevenlabs_agent_id_immo", agent_id)

        if agent_profile:
            agent_profile.sudo().write(
                {
                    "name": "Maison Recherchée · J+0 Qualification",
                    "immo_agent_role": "j0_qualification",
                    "provider": "elevenlabs",
                    "external_agent_id": agent_id,
                    "voice_clone_id": voice_id,
                    "voice_name": VOICE_CLONE_NAME,
                    "transfer_phone": TRANSFER_NUMBER,
                    "default_volet": "qualification",
                    "agent_type": "outbound",
                    "pipeline": "immobilier",
                    "timezone": "America/Toronto",
                    "status": "active",
                    "system_prompt": SOPHIE_SYSTEM_PROMPT,
                }
            )
            for phone in agent_profile.phone_number_ids:
                phone.write(
                    {
                        "twilio_sip_trunk_sid": SIP_TRUNK_SID,
                        "phone_number": FROM_NUMBER,
                        "sip_trunk_name": "Digital Doorway-4387905970",
                    }
                )
            try:
                ph_id = self.client.ensure_twilio_phone_number(
                    FROM_NUMBER,
                    agent_id=agent_id,
                    label=AGENT_CONVAI_NAME,
                )
                self.icp.set_param(
                    "doorway_agents_dashboard.elevenlabs_phone_number_id", ph_id
                )
                agent_profile.phone_number_ids.write(
                    {"elevenlabs_phone_number_id": ph_id}
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Import numéro Twilio ElevenLabs: %s", exc)

        test_path = ""
        try:
            test_path = self.test_voice_tts(voice_id)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Test TTS Sophie: %s", exc)

        relance_ids = {}
        try:
            relance_ids = self.create_relance_agents(voice_id, update_existing=update_existing)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Agents relance (optionnel): %s", exc)

        return {
            "voice_id": voice_id,
            "agent_id": agent_id,
            "relance_agents": relance_ids,
            "test_audio_path": test_path,
            "from_number": FROM_NUMBER,
            "sip_trunk_sid": SIP_TRUNK_SID,
            "transfer_number": TRANSFER_NUMBER,
            "n8n_postcall_url": self._n8n_postcall_url(),
        }
