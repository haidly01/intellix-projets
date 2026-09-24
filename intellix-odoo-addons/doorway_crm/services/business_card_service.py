# -*- coding: utf-8 -*-
"""Extraction des champs d'une carte de visite via Claude Vision (Anthropic)."""
import base64
import json
import logging
import re

import requests

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
VISION_MODEL = "claude-haiku-4-5-20251001"
MAX_IMAGE_BYTES = 8 * 1024 * 1024

API_KEY_PARAMS = (
    "doorway_leads_bruts.claude_api_key",
    "doorway_agents_ia.anthropic_api_key",
    "doorway_agents_dashboard.anthropic_api_key",
    "renovation_conciergerie.anthropic_api_key",
    "doorway_traffic_manager.anthropic_api_key",
    "doorway_social_ia.anthropic_api_key",
)

SYSTEM_PROMPT = (
    "Tu analyses des photos de cartes de visite professionnelles. "
    "Réponds UNIQUEMENT en JSON valide, sans markdown ni commentaire."
)

USER_PROMPT = (
    "Extrais toutes les informations lisibles de cette carte de visite. "
    "Réponds avec ce JSON (chaînes vides si absent) :\n"
    "{\n"
    '  "full_name": "",\n'
    '  "first_name": "",\n'
    '  "last_name": "",\n'
    '  "company": "",\n'
    '  "job_title": "",\n'
    '  "email": "",\n'
    '  "phone": "",\n'
    '  "mobile": "",\n'
    '  "website": "",\n'
    '  "street": "",\n'
    '  "city": "",\n'
    '  "zip": "",\n'
    '  "country_code": ""\n'
    "}\n"
    "Normalise les téléphones au format international si possible (+33, +1, +212…)."
)


def get_api_key(env):
    icp = env["ir.config_parameter"].sudo()
    for param in API_KEY_PARAMS:
        key = (icp.get_param(param) or "").strip()
        if key:
            return key
    return ""


def _parse_json(raw):
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _normalize_parsed(data):
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, val in data.items():
        out[key] = (str(val or "").strip()) if val is not None else ""
    name = out.get("full_name") or " ".join(
        p for p in (out.get("first_name"), out.get("last_name")) if p
    ).strip()
    out["full_name"] = name
    phone = out.get("phone") or out.get("mobile") or ""
    mobile = out.get("mobile") or ""
    if not out.get("phone") and mobile:
        out["phone"] = mobile
    elif phone and not mobile:
        out["mobile"] = ""
    if out.get("website") and not out["website"].startswith(("http://", "https://")):
        out["website"] = "https://" + out["website"].lstrip("/")
    return out


class BusinessCardService:
    def __init__(self, env):
        self.env = env

    def parse_image(self, datas, mimetype="image/jpeg"):
        """Decode base64 image and return structured contact fields."""
        api_key = get_api_key(self.env)
        if not api_key:
            return None, (
                "Clé API Claude (Anthropic) non configurée. "
                "Contactez un administrateur IntelliX."
            )
        raw_b64 = (datas or "").strip()
        if raw_b64.startswith("data:"):
            raw_b64 = raw_b64.split(",", 1)[-1]
        try:
            raw_bytes = base64.b64decode(raw_b64, validate=True)
        except Exception:  # noqa: BLE001
            return None, "Image illisible ou format invalide."
        if not raw_bytes:
            return None, "Image vide."
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            return None, "Image trop volumineuse (max 8 Mo)."
        media_type = (mimetype or "image/jpeg").split(";")[0].strip().lower()
        if not media_type.startswith("image/"):
            media_type = "image/jpeg"
        payload = {
            "model": VISION_MODEL,
            "max_tokens": 1200,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.b64encode(raw_bytes).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=90,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("business_card vision network: %s", exc)
            return None, "Service IA injoignable. Réessayez."
        if resp.status_code != 200:
            _logger.warning("business_card vision HTTP %s: %s", resp.status_code, resp.text[:300])
            return None, "Analyse de la carte impossible (erreur IA)."
        try:
            parts = resp.json().get("content") or []
            raw = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        except Exception:  # noqa: BLE001
            return None, "Réponse IA illisible."
        parsed = _normalize_parsed(_parse_json(raw))
        if not parsed:
            return None, "Impossible de lire la carte. Reprenez la photo en lumière directe."
        if not any(parsed.get(k) for k in ("full_name", "company", "email", "phone", "mobile")):
            return None, "Aucune information exploitable détectée sur la carte."
        return parsed, "Carte analysée."

    @staticmethod
    def phone_digits(phone):
        return re.sub(r"\D", "", phone or "")
