# -*- coding: utf-8 -*-
"""Client API ElevenLabs — agents, appels Twilio, transcriptions."""
import json
import logging
from io import BytesIO

import requests

from odoo import _, fields
from odoo.exceptions import UserError

from .config_loader import get_secret
from .elevenlabs_voicemail import TELEPHONY_OUTBOUND_CONFIG, inject_voicemail_detection

_logger = logging.getLogger(__name__)

BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsClient:
    def __init__(self, env=None):
        self.env = env
        api_key = get_secret(
            env,
            "ELEVENLABS_API_KEY",
            "doorway_agents_dashboard.elevenlabs_api_key",
            ["doorway_agents_dashboard.elevenlabs_api_key"],
        )
        self.headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }

    def list_agents(self):
        """Retourne liste agents ElevenLabs."""
        r = requests.get(
            "%s/convai/agents" % BASE,
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("agents", [])

    _LANG_VOICE_HINTS = {
        "fr": ("french", "france", "français", "quebec", "québécois", "canadian"),
        "en": ("english", "american", "british", "australian", "irish"),
        "es": ("spanish", "español", "mexican", "latin", "castilian"),
    }

    _PREVIEW_TEXT = {
        "fr": (
            "Bonjour, je suis votre agent Intellix. "
            "Je suis prêt à qualifier vos prospects."
        ),
        "en": (
            "Hello, I am your Intellix agent. "
            "I am ready to qualify your leads."
        ),
        "es": (
            "Hola, soy su agente Intellix. "
            "Estoy listo para calificar sus prospectos."
        ),
        "bilingual": (
            "Bonjour / Hello, je suis votre agent Intellix bilingue."
        ),
    }

    def _voice_matches_language(self, voice, language):
        if not language or language == "bilingual":
            return True
        labels = voice.get("labels") or {}
        lang_label = (
            labels.get("language") or voice.get("language") or ""
        ).lower()
        lang_codes = {
            "fr": ("fr", "fre", "fra", "french"),
            "en": ("en", "eng", "english"),
            "es": ("es", "spa", "spanish"),
        }
        if lang_label in lang_codes.get(language, (language,)):
            return True
        blob = " ".join(
            str(labels.get(k) or "")
            for k in ("accent", "language", "description", "gender", "locale")
        ).lower()
        name = (voice.get("name") or "").lower()
        locale = (voice.get("locale") or labels.get("locale") or "").lower()
        hints = self._LANG_VOICE_HINTS.get(language, ())
        return any(
            h in blob or h in name or h in locale for h in hints
        )

    def _voice_matches_gender(self, voice, gender):
        if not gender or gender == "any":
            return True
        labels = voice.get("labels") or {}
        g = (labels.get("gender") or "").lower()
        if gender == "female":
            return g in ("female", "woman", "feminine", "f")
        if gender == "male":
            return g in ("male", "man", "masculine", "m")
        return True

    @staticmethod
    def extract_recording_url(call_data):
        if not call_data:
            return ""
        for key in (
            "recording_url",
            "audio_url",
            "recording",
            "call_recording_url",
        ):
            val = call_data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                url = val.get("url") or val.get("recording_url") or ""
                if url:
                    return url
        metadata = call_data.get("metadata") or {}
        if isinstance(metadata, dict):
            return metadata.get("recording_url") or metadata.get("audio_url") or ""
        return ""

    def _voice_row_from_shared(self, voice):
        locale = voice.get("locale") or ""
        desc = (
            voice.get("description")
            or voice.get("accent")
            or locale
            or voice.get("use_case")
            or ""
        )
        return {
            "voice_id": voice.get("voice_id") or "",
            "public_owner_id": voice.get("public_owner_id") or "",
            "name": voice.get("name") or "",
            "description": desc,
            "preview_url": voice.get("preview_url") or "",
            "category": voice.get("category") or "shared",
            "is_clone": voice.get("category") == "cloned",
            "is_shared": True,
            "gender": (voice.get("gender") or "").lower(),
            "locale": locale,
        }

    def _voice_row_from_account(self, voice):
        labels = voice.get("labels") or {}
        desc = (
            labels.get("description")
            or labels.get("accent")
            or labels.get("language")
            or labels.get("gender")
            or voice.get("locale")
            or ""
        )
        return {
            "voice_id": voice.get("voice_id") or "",
            "public_owner_id": "",
            "name": voice.get("name") or "",
            "description": desc,
            "preview_url": voice.get("preview_url") or "",
            "category": voice.get("category") or "",
            "is_clone": voice.get("category") == "cloned",
            "is_shared": False,
            "gender": (labels.get("gender") or voice.get("gender") or "").lower(),
            "locale": voice.get("locale") or labels.get("locale") or "",
        }

    def _fetch_shared_voices(self, language=None, gender=None, locale=None, page_size=40):
        """Bibliothèque publique ElevenLabs (voix prédéfinies + communauté)."""
        params = {"page_size": page_size}
        if language and language != "bilingual":
            params["language"] = language
        if gender and gender != "any":
            params["gender"] = gender
        if locale:
            params["locale"] = locale
        try:
            r = requests.get(
                "%s/shared-voices" % BASE,
                headers=self.headers,
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("voices") or []
        except requests.RequestException as exc:
            _logger.warning("ElevenLabs shared-voices: %s", exc)
            return []

    def list_voices_for_wizard(
        self, language=None, cloned_voice=None, gender=None, locale=None
    ):
        """Voix ElevenLabs pour la grille du wizard (cards)."""
        rows = []
        seen = set()
        clone_id = (cloned_voice or {}).get("voice_id")

        if clone_id:
            seen.add(clone_id)
            rows.append(
                {
                    "voice_id": clone_id,
                    "public_owner_id": "",
                    "name": cloned_voice.get("name") or _("Ma voix clonée"),
                    "description": _("Voix clonée — recommandée"),
                    "preview_url": "",
                    "category": "cloned",
                    "is_clone": True,
                    "is_shared": False,
                    "gender": "",
                    "locale": "",
                }
            )

        if not self.is_available():
            return rows

        for voice in self._fetch_shared_voices(language, gender, locale):
            vid = voice.get("voice_id") or ""
            if not vid or vid in seen:
                continue
            seen.add(vid)
            rows.append(self._voice_row_from_shared(voice))
            if len(rows) >= 48:
                return rows

        try:
            r = requests.get("%s/voices" % BASE, headers=self.headers, timeout=15)
            r.raise_for_status()
            account_voices = r.json().get("voices") or []
        except requests.RequestException as exc:
            _logger.warning("ElevenLabs list_voices: %s", exc)
            return rows

        matched, fallback = [], []
        for voice in account_voices:
            vid = voice.get("voice_id") or ""
            if not vid or vid in seen:
                continue
            lang_ok = (
                not language
                or language == "bilingual"
                or self._voice_matches_language(voice, language)
            )
            gender_ok = self._voice_matches_gender(voice, gender)
            if locale:
                voice_locale = (
                    voice.get("locale")
                    or (voice.get("labels") or {}).get("locale")
                    or ""
                )
                if voice_locale and voice_locale != locale:
                    continue
            row = self._voice_row_from_account(voice)
            if lang_ok and gender_ok:
                matched.append(row)
            else:
                fallback.append(row)

        pool = matched if matched else fallback
        for row in pool:
            seen.add(row["voice_id"])
            rows.append(row)
            if len(rows) >= 48:
                break
        return rows

    def voice_preview_audio(self, voice_id, speed=1.0, stability=0.5, text=None, language=None):
        """Génère un aperçu audio (~10 s) encodé base64."""
        import base64

        if not voice_id:
            raise UserError(_("Voice ID requis."))
        sample = text or self._PREVIEW_TEXT.get(language or "fr", self._PREVIEW_TEXT["fr"])
        url = "%s/text-to-speech/%s" % (BASE, voice_id)
        data = {
            "text": sample[:280],
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": float(stability or 0.5),
                "similarity_boost": 0.85,
                "speed": float(speed or 1.0),
            },
        }
        r = requests.post(url, headers=self.headers, json=data, timeout=30)
        if r.status_code >= 400:
            raise UserError(
                _("Aperçu voix impossible (%s): %s") % (r.status_code, r.text[:300])
            )
        return base64.b64encode(r.content).decode("ascii")

    def create_voice_clone(self, voice_name, audio_content, filename):
        """Crée une voix clonée ElevenLabs depuis un fichier audio."""
        import os

        headers = {
            "xi-api-key": self.headers.get("xi-api-key", ""),
        }
        ext = os.path.splitext(filename or "")[1].lower()
        mime_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
        }
        mime = mime_map.get(ext, "audio/mpeg")
        files = [
            (
                "files",
                (
                    filename or "voice_sample.wav",
                    BytesIO(audio_content),
                    mime,
                ),
            )
        ]
        data = {"name": voice_name}
        r = requests.post(
            "%s/voices/add" % BASE,
            headers=headers,
            data=data,
            files=files,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def sync_agent(self, agent_profile_record):
        """Sync statut et infos d'un agent depuis EL."""
        agent_profile_record.ensure_one()
        try:
            r = requests.get(
                "%s/convai/agents/%s"
                % (BASE, agent_profile_record.external_agent_id),
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
            _logger.warning("ElevenLabs sync_agent: %s", exc)
            agent_profile_record.write({"status": "error"})

    def list_phone_numbers(self):
        r = requests.get(
            "%s/convai/phone-numbers" % BASE,
            headers=self.headers,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("phone_numbers", [])

    def ensure_twilio_phone_number(self, phone_number, agent_id=None, label=None):
        """Importe ou récupère le numéro Twilio natif ElevenLabs (requis pour outbound-call)."""
        phone_number = (phone_number or "").strip()
        if not phone_number:
            raise UserError(_("Numéro émetteur Twilio manquant."))
        label = label or phone_number
        for item in self.list_phone_numbers():
            if (item.get("phone_number") or "").strip() != phone_number:
                continue
            if item.get("provider") != "twilio":
                continue
            ph_id = item.get("phone_number_id") or ""
            if agent_id and ph_id:
                requests.patch(
                    "%s/convai/phone-numbers/%s" % (BASE, ph_id),
                    headers=self.headers,
                    json={"agent_id": agent_id},
                    timeout=15,
                )
            return ph_id
        sid = get_secret(self.env, "TWILIO_ACCOUNT_SID", None, [])
        token = get_secret(self.env, "TWILIO_AUTH_TOKEN", None, [])
        if not sid or not token:
            raise UserError(
                _(
                    "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN requis pour lier "
                    "%(phone)s à ElevenLabs."
                )
                % {"phone": phone_number}
            )
        r = requests.post(
            "%s/convai/phone-numbers" % BASE,
            headers=self.headers,
            json={
                "label": label,
                "phone_number": phone_number,
                "sid": sid,
                "token": token,
            },
            timeout=30,
        )
        if r.status_code >= 400:
            raise UserError(
                _("Échec import numéro Twilio ElevenLabs (%s): %s")
                % (r.status_code, r.text[:500])
            )
        ph_id = (r.json() or {}).get("phone_number_id") or ""
        if agent_id and ph_id:
            requests.patch(
                "%s/convai/phone-numbers/%s" % (BASE, ph_id),
                headers=self.headers,
                json={"agent_id": agent_id},
                timeout=15,
            )
        return ph_id

    def resolve_agent_phone_number_id(self, from_number, agent_profile=None):
        """Résout phnum_… pour outbound-call (ICP, ligne agent, ou import Twilio)."""
        icp = self.env["ir.config_parameter"].sudo()
        ph_id = (icp.get_param("doorway_agents_dashboard.elevenlabs_phone_number_id") or "").strip()
        if agent_profile and agent_profile.phone_number_ids:
            line = agent_profile.phone_number_ids.filtered(
                lambda p: (p.phone_number or "").strip() == (from_number or "").strip()
                and p.elevenlabs_phone_number_id
            )[:1]
            if not line:
                line = agent_profile.phone_number_ids.filtered(
                    lambda p: p.elevenlabs_phone_number_id
                )[:1]
            if line:
                ph_id = (line.elevenlabs_phone_number_id or "").strip() or ph_id
        if ph_id:
            return ph_id
        agent_id = (agent_profile.external_agent_id or "").strip() if agent_profile else ""
        ph_id = self.ensure_twilio_phone_number(
            from_number,
            agent_id=agent_id or None,
            label=(agent_profile.name if agent_profile else None) or from_number,
        )
        icp.set_param("doorway_agents_dashboard.elevenlabs_phone_number_id", ph_id)
        if agent_profile and agent_profile.phone_number_ids:
            agent_profile.phone_number_ids.filtered(
                lambda p: (p.phone_number or "").strip() == (from_number or "").strip()
            ).write({"elevenlabs_phone_number_id": ph_id})
        return ph_id

    def is_available(self):
        return bool((self.headers.get("xi-api-key") or "").strip())

    @staticmethod
    def parse_api_error(response):
        """Message lisible (FR) à partir d'une réponse ElevenLabs >= 400."""
        status = getattr(response, "status_code", 0) or 0
        raw = (getattr(response, "text", None) or "")[:800]
        detail = {}
        try:
            detail = (json.loads(raw).get("detail") or {}) if raw else {}
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        if isinstance(detail, list):
            detail = detail[0] if detail else {}
        code = detail.get("code") or detail.get("status") or ""
        message = detail.get("message") or raw[:300]
        if code == "voice_not_found":
            voice_hint = ""
            marker = "voice_id "
            if marker in (message or ""):
                voice_hint = message.split(marker, 1)[-1].strip().rstrip(".")
            return _(
                "Voix ElevenLabs introuvable ou non activée sur votre compte"
                "%(voice)s.\n\n"
                "Les voix de la bibliothèque publique doivent être ajoutées à "
                "votre compte avant de créer un agent conversationnel. "
                "Resélectionnez la voix dans l'étape « Voix » du wizard, ou "
                "choisissez une voix déjà présente sur le compte "
                "(ex. Sophie / Léa FR)."
            ) % {"voice": (" (%s)" % voice_hint) if voice_hint else ""}
        if code == "voice_access_denied":
            return _(
                "Accès refusé à cette voix ElevenLabs. Choisissez une autre voix "
                "ou vérifiez votre abonnement."
            )
        return _("Erreur ElevenLabs (%(status)s): %(message)s") % {
            "status": status,
            "message": message or raw[:200],
        }

    def _list_account_voice_ids(self):
        if not self.is_available():
            return set()
        try:
            r = requests.get("%s/voices" % BASE, headers=self.headers, timeout=15)
            r.raise_for_status()
        except requests.RequestException as exc:
            _logger.warning("ElevenLabs list account voices: %s", exc)
            return set()
        return {
            (v.get("voice_id") or "").strip()
            for v in (r.json().get("voices") or [])
            if (v.get("voice_id") or "").strip()
        }

    def _find_shared_voice_meta(self, voice_id):
        """Cherche une voix bibliothèque publique (owner id requis pour l'ajout)."""
        voice_id = (voice_id or "").strip()
        if not voice_id or not self.is_available():
            return {}
        params = {"page_size": 100, "search": voice_id}
        try:
            r = requests.get(
                "%s/shared-voices" % BASE,
                headers=self.headers,
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            for voice in r.json().get("voices") or []:
                if (voice.get("voice_id") or "").strip() == voice_id:
                    return voice
        except requests.RequestException as exc:
            _logger.warning("ElevenLabs shared-voice lookup %s: %s", voice_id, exc)
        return {}

    def _add_shared_voice_to_library(self, public_owner_id, voice_id, new_name):
        public_owner_id = (public_owner_id or "").strip()
        voice_id = (voice_id or "").strip()
        new_name = (new_name or _("Voix agent Intellix")).strip()[:80]
        if not public_owner_id or not voice_id:
            return False
        url = "%s/voices/add/%s/%s" % (BASE, public_owner_id, voice_id)
        try:
            r = requests.post(
                url,
                headers=self.headers,
                json={"new_name": new_name},
                timeout=30,
            )
        except requests.RequestException as exc:
            _logger.warning("ElevenLabs add shared voice %s: %s", voice_id, exc)
            return False
        if r.status_code >= 400:
            _logger.warning(
                "ElevenLabs add shared voice %s (%s): %s",
                voice_id,
                r.status_code,
                r.text[:300],
            )
            return False
        _logger.info("Voix bibliothèque ajoutée au compte EL: %s", voice_id)
        return True

    def ensure_voice_for_convai(self, voice_id, voice_name=None, public_owner_id=None):
        """Garantit que la voix est utilisable pour ConvAI (compte ou bibliothèque)."""
        voice_id = (voice_id or "").strip()
        if not voice_id:
            raise UserError(_("Voice ID manquant."))
        if not self.is_available():
            raise UserError(_("Clé API ElevenLabs non configurée."))
        if voice_id in self._list_account_voice_ids():
            return voice_id
        owner = (public_owner_id or "").strip()
        shared = {}
        if not owner:
            shared = self._find_shared_voice_meta(voice_id)
            owner = (shared.get("public_owner_id") or "").strip()
        label = voice_name or (shared.get("name") if shared else None) or voice_id
        if owner and self._add_shared_voice_to_library(owner, voice_id, label):
            if voice_id in self._list_account_voice_ids():
                return voice_id
        raise UserError(
            _(
                "Voix ElevenLabs « %(name)s » (%(voice)s) introuvable ou non "
                "activée sur votre compte.\n\n"
                "Si vous venez de la bibliothèque publique, resélectionnez-la "
                "dans l'étape « Voix » (ajout automatique) ou choisissez une "
                "voix déjà sur le compte (Sophie, Léa FR, Caroline…)."
            )
            % {"name": label, "voice": voice_id}
        )

    def fetch_agent_prompt_bundle(self, agent_id):
        """Retourne prompt + first_message stockés sur un agent ConvAI."""
        if not self.is_available() or not (agent_id or "").strip():
            return {}
        try:
            r = requests.get(
                "%s/convai/agents/%s" % (BASE, agent_id.strip()),
                headers=self.headers,
                timeout=20,
            )
            if r.status_code >= 400:
                return {}
            agent_cfg = (r.json().get("conversation_config") or {}).get("agent") or {}
            return {
                "prompt": (agent_cfg.get("prompt") or {}).get("prompt") or "",
                "first_message": agent_cfg.get("first_message") or "",
            }
        except requests.RequestException as exc:
            _logger.warning("fetch_agent_prompt_bundle: %s", exc)
            return {}

    @staticmethod
    def _web_test_override_platform_settings():
        return {
            "overrides": {
                "conversation_config_override": {
                    "agent": {
                        "first_message": True,
                        "language": True,
                        "prompt": {
                            "prompt": True,
                        },
                    },
                },
            },
        }

    def enable_web_test_overrides(self, agent_id):
        """Autorise prompt / first_message overrides pour les tests navigateur Odoo."""
        if not self.is_available() or not (agent_id or "").strip():
            return False
        payload = {
            "platform_settings": self._web_test_override_platform_settings(),
        }
        try:
            r = requests.patch(
                "%s/convai/agents/%s" % (BASE, agent_id.strip()),
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            if r.status_code >= 400:
                _logger.warning(
                    "enable_web_test_overrides %s: %s",
                    agent_id,
                    r.text[:300],
                )
                return False
            return True
        except requests.RequestException as exc:
            _logger.warning("enable_web_test_overrides: %s", exc)
            return False

    def patch_web_test_turn_timeouts(self, agent_id):
        """Évite les coupures précoces pendant le test navigateur (agent lent à démarrer)."""
        if not self.is_available() or not (agent_id or "").strip():
            return False
        payload = {
            "conversation_config": {
                "turn": {
                    "turn_timeout": 12,
                    "silence_end_call_timeout": 45,
                },
                "conversation": {"max_duration_seconds": 300},
            },
        }
        try:
            r = requests.patch(
                "%s/convai/agents/%s" % (BASE, agent_id.strip()),
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            return r.status_code < 400
        except requests.RequestException as exc:
            _logger.warning("patch_web_test_turn_timeouts: %s", exc)
            return False

    def force_web_test_agent_config(
        self, agent_id, prompt, first_message=None, language="fr"
    ):
        """Écrase prompt + ouverture sur l'agent EL juste avant le test (source de vérité Odoo)."""
        if not self.is_available() or not (agent_id or "").strip():
            return False
        prompt = (prompt or "").strip()
        if not prompt:
            return False
        agent_cfg = {
            "prompt": {
                "prompt": prompt,
                "max_tokens": 500,
                "temperature": 0.35,
                "ignore_default_personality": True,
            },
            "language": language or "fr",
        }
        if first_message:
            agent_cfg["first_message"] = first_message
        payload = {
            "conversation_config": {"agent": agent_cfg},
            "platform_settings": self._web_test_override_platform_settings(),
        }
        try:
            r = requests.patch(
                "%s/convai/agents/%s" % (BASE, agent_id.strip()),
                headers=self.headers,
                json=payload,
                timeout=60,
            )
            if r.status_code >= 400:
                _logger.warning(
                    "force_web_test_agent_config %s: %s",
                    agent_id,
                    r.text[:400],
                )
                return False
            return True
        except requests.RequestException as exc:
            _logger.warning("force_web_test_agent_config: %s", exc)
            return False

    def get_conversation_token(self, agent_id, dynamic_variables=None):
        """Token WebRTC ou signed URL pour test navigateur ConvAI."""
        if not self.is_available():
            return {"ok": False, "message": "Clé ElevenLabs absente."}
        if not (agent_id or "").strip():
            return {"ok": False, "message": "agent_id manquant."}
        params = {"agent_id": agent_id.strip()}
        try:
            r = requests.get(
                "%s/convai/conversation/token" % BASE,
                headers=self.headers,
                params=params,
                timeout=20,
            )
            if r.status_code >= 400:
                r2 = requests.get(
                    "%s/convai/conversation/get-signed-url" % BASE,
                    headers=self.headers,
                    params=params,
                    timeout=20,
                )
                if r2.status_code >= 400:
                    return {
                        "ok": False,
                        "message": _("ElevenLabs (%s): %s")
                        % (r.status_code, (r.text or r2.text)[:300]),
                    }
                body = r2.json()
                return {
                    "ok": True,
                    "signed_url": body.get("signed_url") or "",
                    "conversation_token": "",
                }
            body = r.json()
            token = body.get("token") or body.get("conversation_token") or ""
            return {"ok": True, "conversation_token": token, "signed_url": ""}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def fetch_conversation_transcript(self, conversation_id):
        if not self.is_available() or not conversation_id:
            return ""
        try:
            r = requests.get(
                "%s/convai/conversations/%s" % (BASE, conversation_id),
                headers=self.headers,
                timeout=20,
            )
            if r.status_code >= 400:
                return ""
            return self.extract_transcript(r.json())
        except requests.RequestException:
            return ""

    def start_phone_call(
        self,
        agent_id,
        to_number,
        from_number,
        dynamic_variables=None,
        agent_profile=None,
    ):
        """Lance appel téléphonique via Twilio + ElevenLabs (API agent_phone_number_id)."""
        agent_phone_number_id = self.resolve_agent_phone_number_id(
            from_number, agent_profile=agent_profile
        )
        if not agent_phone_number_id:
            raise UserError(
                _(
                    "Aucun phone_number_id ElevenLabs pour %(from)s. "
                    "Relancez Setup ElevenLabs ou importez le numéro Twilio dans la console EL."
                )
                % {"from": from_number}
            )
        payload = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id,
            "to_number": to_number,
            "conversation_initiation_client_data": {
                "dynamic_variables": dynamic_variables or {},
            },
            "telephony_call_config": dict(TELEPHONY_OUTBOUND_CONFIG),
        }
        r = requests.post(
            "%s/convai/twilio/outbound-call" % BASE,
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        if r.status_code >= 400:
            raise UserError(
                _("Échec appel ElevenLabs (%s): %s") % (r.status_code, r.text[:500])
            )
        return r.json()

    def sync_voicemail_detection_on_agent(self, agent_id):
        """Active voicemail_detection (raccrochage sans message) sur un agent ConvAI."""
        if not agent_id or not str(agent_id).startswith("agent_"):
            return False
        payload = inject_voicemail_detection({})
        r = requests.patch(
            "%s/convai/agents/%s" % (BASE, agent_id),
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if r.status_code >= 400:
            _logger.warning(
                "voicemail_detection %s: %s %s",
                agent_id,
                r.status_code,
                r.text[:300],
            )
            return False
        return True

    def sync_voicemail_detection_all_outbound(self):
        """Applique la détection répondeur à tous les agents ElevenLabs (profils + ICP)."""
        icp = self.env["ir.config_parameter"].sudo()
        agent_ids = set()
        for row in icp.search(
            [("key", "=like", "doorway_agents_dashboard.elevenlabs_agent_id%")]
        ):
            val = (row.value or "").strip()
            if val.startswith("agent_"):
                agent_ids.add(val)
        Profile = self.env["doorway.agent.profile"].sudo()
        for rec in Profile.search([("provider", "=", "elevenlabs")]):
            eid = (rec.external_agent_id or "").strip()
            if eid.startswith("agent_"):
                agent_ids.add(eid)
        ok = 0
        for agent_id in sorted(agent_ids):
            if self.sync_voicemail_detection_on_agent(agent_id):
                ok += 1
        return {"updated": ok, "total": len(agent_ids)}

    def get_call_transcript(self, call_id):
        """Récupère transcription après fin appel."""
        r = requests.get(
            "%s/convai/calls/%s" % (BASE, call_id),
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # --- Adaptateurs Odoo ---

    def _from_number(self):
        return get_secret(
            self.env,
            "TWILIO_FROM_NUMBER",
            "doorway_agents_dashboard.elevenlabs_from_number",
            [
                "doorway_agents_dashboard.twilio_phone_number",
                "renovation_conciergerie.retell_from_number",
            ],
        )

    def sync_profiles(self):
        if not self.is_available():
            return 0
        try:
            agents = self.list_agents()
        except requests.RequestException as exc:
            _logger.warning("ElevenLabs sync_profiles: %s", exc)
            return 0
        Profile = self.env["doorway.agent.profile"].sudo()
        count = 0
        seen = set()
        for item in agents:
            agent_id = item.get("agent_id") or item.get("id")
            if not agent_id or agent_id in seen:
                continue
            seen.add(agent_id)
            name = item.get("name") or agent_id
            api_lang = item.get("language") or item.get("default_language") or ""
            vals = {
                "name": name,
                "provider": "elevenlabs",
                "external_agent_id": agent_id,
                "pipeline": Profile._infer_pipeline(name),
                "agent_type": Profile._infer_agent_type(name),
                "language": Profile._infer_language(name, api_lang),
                "voice_name": item.get("voice_id") or "",
                "description": item.get("description") or False,
                "status": "active",
                "last_sync": fields.Datetime.now(),
            }
            existing = Profile.search(
                [
                    ("provider", "=", "elevenlabs"),
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
        """Lance un appel test depuis un enregistrement doorway.agent.test.call."""
        test_call.ensure_one()
        if not self.is_available():
            return {"ok": False, "message": "Clé ElevenLabs absente."}
        to_number = (test_call.phone_number or "").strip()
        if not to_number:
            return {"ok": False, "message": "Numéro de téléphone requis."}
        from_number = self._from_number()
        if not from_number:
            return {
                "ok": False,
                "message": "Numéro émetteur Twilio manquant (ELEVENLABS / paramètres Odoo).",
            }
        try:
            dynamic_variables = {}
            if hasattr(test_call, "_elevenlabs_dynamic_variables"):
                dynamic_variables = test_call._elevenlabs_dynamic_variables()
            body = self.start_phone_call(
                test_call.agent_id.external_agent_id,
                to_number,
                from_number,
                dynamic_variables=dynamic_variables,
                agent_profile=test_call.agent_id,
            )
            ext_id = (
                body.get("conversation_id")
                or body.get("call_id")
                or body.get("id")
            )
            return {
                "ok": True,
                "external_call_id": ext_id,
                "state": "in_progress",
                "raw": body,
            }
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

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
                msg = turn.get("message") or turn.get("text") or turn.get("content") or ""
                lines.append("%s: %s" % (role, msg))
            return "\n".join(lines)
        return call_data.get("transcription") or ""
