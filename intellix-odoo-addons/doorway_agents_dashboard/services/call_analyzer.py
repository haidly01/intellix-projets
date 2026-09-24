# -*- coding: utf-8 -*-
"""Analyse post-appel test via Claude Sonnet."""
import json
import logging

import requests

from .config_loader import get_secret

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
SONNET_MODEL = "claude-sonnet-4-20250514"

SCORING_SYSTEM = """Tu es un expert en qualité d'agents IA vocaux pour call center québécois.
Évalue cette transcription d'appel test selon 4 critères (note /20 chacun):
1. fluidite: naturel conversation, pas de répétitions ou silences gênants
2. pertinence: réponses adaptées au contexte, objections bien gérées
3. conversion: capacité à qualifier le lead et pousser vers l'action
4. tone: professionnalisme, chaleur, adaptation au client québécois
Réponds UNIQUEMENT en JSON valide, aucun texte avant/après:
{"score_fluidite": X.X, "score_pertinence": X.X, "score_conversion": X.X, "score_tone": X.X,
 "forces": ["...", "..."], "faiblesses": ["...", "..."], "recommandations": ["...", "..."]}"""


def _api_key(env=None):
    return get_secret(
        env,
        "ANTHROPIC_API_KEY",
        "doorway_agents_dashboard.anthropic_api_key",
        [
            "doorway_agents_dashboard.anthropic_api_key",
            "renovation_conciergerie.anthropic_api_key",
        ],
    )


def analyze_call(transcript, agent_context="", api_key=None):
    """Analyse une transcription et retourne le dict JSON de scoring."""
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {}
    prompt = "Contexte agent: %s\n\nTRANSCRIPTION:\n%s" % (
        agent_context or "Non spécifié",
        transcript,
    )
    r = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": SONNET_MODEL,
            "max_tokens": 1000,
            "system": SCORING_SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    r.raise_for_status()
    content = r.json()["content"][0]["text"]
    try:
        return json.loads(content)
    except (TypeError, ValueError, KeyError, IndexError):
        parsed = _extract_json(content)
        if parsed:
            return parsed
        _logger.error("Claude response not JSON: %s", content)
        return {}


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


class CallAnalyzer:
    def __init__(self, env):
        self.env = env
        self._api_key = _api_key(env)

    def is_available(self):
        return bool(self._api_key)

    def analyze_test_call(self, test_call):
        test_call.ensure_one()
        transcript = (test_call.transcript or "").strip()
        if not transcript:
            return {"ok": False, "message": "Transcription vide."}
        if not self.is_available():
            return {
                "ok": True,
                "analyse_ia": "Analyse IA indisponible (clé Anthropic absente).",
                "score_fluidite": 0.0,
                "score_pertinence": 0.0,
                "score_conversion": 0.0,
                "score_tone": 0.0,
                "forces": [],
                "faiblesses": [],
                "recommandations": [],
            }
        agent = test_call.agent_id
        context_parts = [
            "Agent: %s" % (agent.name or ""),
            "Provider: %s" % (agent.provider or ""),
            "Pipeline: %s" % (agent.pipeline or ""),
            "Type: %s" % (agent.agent_type or ""),
        ]
        if test_call.scenario_hint:
            context_parts.append("Scénario: %s" % test_call.scenario_hint.strip())
        agent_context = " | ".join(p for p in context_parts if p)
        try:
            parsed = analyze_call(
                transcript[:12000],
                agent_context=agent_context,
                api_key=self._api_key,
            )
            if not parsed:
                return {"ok": False, "message": "Réponse Claude invalide (JSON attendu)."}
            total = sum(
                float(parsed.get(k) or 0)
                for k in (
                    "score_fluidite",
                    "score_pertinence",
                    "score_conversion",
                    "score_tone",
                )
            )
            return {
                "ok": True,
                "analyse_ia": (
                    "Score global %s/100 — Fluidité %s, Pertinence %s, "
                    "Conversion %s, Ton %s."
                )
                % (
                    total,
                    parsed.get("score_fluidite", 0),
                    parsed.get("score_pertinence", 0),
                    parsed.get("score_conversion", 0),
                    parsed.get("score_tone", 0),
                ),
                "score_fluidite": float(parsed.get("score_fluidite") or 0),
                "score_pertinence": float(parsed.get("score_pertinence") or 0),
                "score_conversion": float(parsed.get("score_conversion") or 0),
                "score_tone": float(parsed.get("score_tone") or 0),
                "forces": parsed.get("forces") or [],
                "faiblesses": parsed.get("faiblesses") or [],
                "recommandations": parsed.get("recommandations") or [],
            }
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}
