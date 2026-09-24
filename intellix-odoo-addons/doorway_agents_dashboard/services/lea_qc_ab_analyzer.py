# -*- coding: utf-8 -*-
"""Analyse Claude post-appel Léa-QC — accélération A/B (fail-open)."""
import json
import logging

import requests

from .config_loader import get_secret

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

AB_SYSTEM = """Tu es évaluateur QA pour Léa, agent vocal IA québécois (Soumission Entrepreneurs).
Léa qualifie propriétaires (réno / immo) via un script déterministe avec variantes A/B de répliques.

Variante A = script contrôle (accroche standard).
Variante B = accroche orientée bénéfice / évaluation gratuite.

Analyse la transcription et le contexte. Réponds UNIQUEMENT en JSON valide :
{
  "comprehension_score": float 0-10,
  "routing_errors": ["..."],
  "variant_winner_hint": "A"|"B"|"tie"|"unclear",
  "suggested_fixes": ["..."],
  "quality_flags": ["silence"|"timeout"|"stt_error"|"early_hangup"|"wrong_routing"|"objection_missed"|"tone_issue"|"..."]
}

comprehension_score = clarté du dialogue, adéquation des réponses au prospect, fluidité.
routing_errors = erreurs d'aiguillage script (ex: locataire traité comme proprio, mauvaise branche).
variant_winner_hint = quel script semble mieux pour CET appel (pas statistique globale).
suggested_fixes = actions concrètes pour améliorer le script ou le flux.
quality_flags = signaux techniques ou UX dégradée observés dans le transcript."""


def _api_key(env):
    return get_secret(
        env,
        "ANTHROPIC_API_KEY",
        "doorway_agents_dashboard.anthropic_api_key",
        [
            "doorway_agents_dashboard.anthropic_api_key",
            "renovation_conciergerie.anthropic_api_key",
            "doorway_agents_ia.anthropic_api_key",
        ],
    )


def _extract_json(text):
    text = (text or "").strip()
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (TypeError, ValueError):
            pass
    return {}


class LeaQcAbAnalyzer:
    """Appelle Claude pour scorer un appel Léa-QC (jamais bloquant pour le flux appel)."""

    def __init__(self, env):
        self.env = env
        self._api_key = _api_key(env)
        icp = env["ir.config_parameter"].sudo()
        model = icp.get_param("lea_qc.ab_analyzer_model", HAIKU_MODEL)
        self._model = model or HAIKU_MODEL

    def is_available(self):
        return bool(self._api_key)

    def analyze_call_record(self, call):
        """Analyse un lea.qc.sample.call ; retourne dict ou {} si échec."""
        call.ensure_one()
        transcript = (call.transcript or "").strip()
        if not transcript and call.turn_ids:
            parts = []
            for t in call.turn_ids.sorted("turn_index"):
                if t.prospect_transcript:
                    parts.append("Prospect: %s" % t.prospect_transcript)
                if t.bot_text:
                    parts.append("Léa: %s" % t.bot_text)
            transcript = "\n".join(parts)
        if not transcript:
            return {"error": "transcript_empty"}
        if not self.is_available():
            return {"error": "anthropic_key_missing"}

        variant = call.variant or "?"
        user = (
            "Variante script: %s\n"
            "Connecté: %s | Qualifié: %s | Durée: %ss | Issue: %s\n"
            "Statut: %s | CRM: %s\n\n"
            "TRANSCRIPT:\n%s"
        ) % (
            variant,
            call.connected,
            call.qualified,
            call.duration_sec or 0,
            call.connect_outcome or "",
            call.statut or "",
            call.crm_action or "",
            transcript[:12000],
        )
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 800,
                    "system": AB_SYSTEM,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=45,
            )
            if resp.status_code != 200:
                _logger.warning(
                    "Léa A/B Claude HTTP %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return {"error": "http_%s" % resp.status_code}
            parts = resp.json().get("content") or []
            raw = "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
            parsed = _extract_json(raw)
            if not parsed:
                return {"error": "invalid_json", "raw": raw[:500]}
            score = parsed.get("comprehension_score")
            try:
                parsed["comprehension_score"] = float(score) if score is not None else 0.0
            except (TypeError, ValueError):
                parsed["comprehension_score"] = 0.0
            parsed.setdefault("routing_errors", [])
            parsed.setdefault("suggested_fixes", [])
            parsed.setdefault("quality_flags", [])
            hint = (parsed.get("variant_winner_hint") or "unclear").upper()
            if hint not in ("A", "B", "TIE", "UNCLEAR"):
                hint = "UNCLEAR"
            parsed["variant_winner_hint"] = hint
            parsed["_model"] = self._model
            return parsed
        except requests.RequestException as exc:
            _logger.warning("Léa A/B Claude: %s", exc)
            return {"error": str(exc)[:200]}
