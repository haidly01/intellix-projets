# -*- coding: utf-8 -*-
"""Claude — test prompt wizard + analyse (Module Performance)."""
import json
import logging

import requests

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
SONNET_MODEL = "claude-sonnet-4-6"


class ClaudeService:
    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _api_key(self):
        return (
            self._icp.get_param("doorway_agents_dashboard.anthropic_api_key")
            or self._icp.get_param("doorway_agents_ia.anthropic_api_key")
            or self._icp.get_param("renovation_conciergerie.anthropic_api_key")
            or ""
        )

    def is_available(self):
        return bool(self._api_key())

    def _call(self, system_prompt, user_content, max_tokens=800):
        key = self._api_key()
        if not key:
            return ""
        headers = {
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": SONNET_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }
        try:
            resp = requests.post(
                ANTHROPIC_URL, headers=headers, data=json.dumps(payload), timeout=60
            )
            if resp.status_code != 200:
                _logger.warning("Claude HTTP %s: %s", resp.status_code, resp.text[:200])
                return ""
            parts = resp.json().get("content") or []
            return "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Claude API: %s", exc)
            return ""

    def test_agent_prompt(self, system_prompt, user_message):
        system = (
            "Tu simules un agent vocal IA pour Intellix CRM (Québec). "
            "Réponds comme l'agent le ferait au téléphone, en français, "
            "de façon naturelle et concise (2-4 phrases max).\n\n"
            "Prompt système de l'agent :\n"
            + (system_prompt or "(vide)")
        )
        return self._call(system, user_message or "Bonjour")

    def analyze_post_call(self, transcript, agent_prompt="", call_id=None):
        """Rapport QA post-appel — utilisé par doorway.call.report."""
        system = (
            "Tu es évaluateur QA pour Agence Doorway. Réponds UNIQUEMENT en JSON valide "
            "avec les clés : score_accroche, score_qualification, score_objections, "
            "score_closing, score_global (float 0-10), points_forts, points_amelioration, "
            "prochaine_action (rappel|email|rdv|archiver), claude_summary."
        )
        if agent_prompt:
            system += "\nScript : " + agent_prompt[:1500]
        raw = self._call(
            system,
            "Transcript complet :\n" + (transcript or "")[:12000],
            max_tokens=1200,
        )
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except json.JSONDecodeError:
            _logger.warning("Claude post-call JSON invalide")
        return {
            "score_global": 0.0,
            "claude_summary": raw or "Analyse non disponible.",
            "prochaine_action": "rappel",
        }

    def analyze_agent_coaching(self, transcriptions, current_prompt=""):
        """Coaching agent : faiblesses + suggestions prompt (30 derniers appels)."""
        if not self.is_available():
            return {
                "weaknesses": [],
                "prompt_suggestions": [],
                "message": "Clé Anthropic absente.",
            }
        lines = []
        for idx, item in enumerate(transcriptions[:30], start=1):
            text = item.get("text") or item if isinstance(item, str) else ""
            if isinstance(item, dict):
                text = item.get("text") or ""
                date = item.get("date") or ""
                lines.append("--- Appel %s (%s) ---\n%s" % (idx, date, text[:2000]))
            else:
                lines.append("--- Appel %s ---\n%s" % (idx, str(text)[:2000]))
        user_content = (
            "Analyse ces transcriptions d'appels et le prompt actuel de l'agent.\n\n"
            "PROMPT ACTUEL :\n%s\n\nTRANSCRIPTIONS :\n%s"
        ) % (current_prompt[:3000], "\n\n".join(lines)[:20000])

        system = (
            "Tu es coach expert en agents vocaux IA (call center Québec). "
            "Réponds UNIQUEMENT en JSON valide avec :\n"
            '- "weaknesses": liste de 3 objets {title, verbatim, frequency} '
            "(verbatim anonymisé, frequency en %)\n"
            '- "prompt_suggestions": liste de 3 à 5 reformulations concrètes '
            "à intégrer au prompt système\n"
            "Langue : français."
        )
        raw = self._call(system, user_content, max_tokens=1500)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                return {
                    "weaknesses": data.get("weaknesses") or [],
                    "prompt_suggestions": data.get("prompt_suggestions") or [],
                }
        except json.JSONDecodeError:
            _logger.warning("Claude coaching JSON invalide: %s", raw[:300])
        return {
            "weaknesses": [
                {
                    "title": "Analyse partielle",
                    "verbatim": (raw or "")[:200],
                    "frequency": 0,
                }
            ],
            "prompt_suggestions": [],
        }

    def analyze_with_user_feedback(
        self,
        transcript="",
        user_comment="",
        rating=3,
        issue_tags=None,
        current_prompt="",
    ):
        """Coaching ciblé à partir d'un test web + commentaire humain."""
        if not self.is_available():
            return {
                "analysis": "Clé Anthropic absente.",
                "weaknesses": [],
                "prompt_suggestions": [],
            }
        issues = ", ".join(issue_tags or []) or "non précisé"
        user_content = (
            "Un superviseur a testé l'agent vocal et donne son retour.\n\n"
            "NOTE UTILISATEUR : %s/5\n"
            "POINTS À AMÉLIORER : %s\n"
            "COMMENTAIRE :\n%s\n\n"
            "TRANSCRIPTION DU TEST :\n%s\n\n"
            "PROMPT SYSTÈME ACTUEL :\n%s"
        ) % (
            rating,
            issues,
            (user_comment or "")[:2000],
            (transcript or "")[:8000],
            (current_prompt or "")[:4000],
        )
        system = (
            "Tu es coach expert en agents vocaux IA (Québec, français). "
            "Réponds UNIQUEMENT en JSON valide :\n"
            '- "analysis": paragraphe court résumant le diagnostic\n'
            '- "weaknesses": liste de 2-4 objets {title, verbatim, frequency}\n'
            '- "prompt_suggestions": liste de 3-5 modifications concrètes du prompt '
            "(phrases prêtes à coller)\n"
            "Priorise le retour humain. Langue : français."
        )
        raw = self._call(system, user_content, max_tokens=1800)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                return {
                    "analysis": data.get("analysis") or "",
                    "weaknesses": data.get("weaknesses") or [],
                    "prompt_suggestions": data.get("prompt_suggestions") or [],
                }
        except json.JSONDecodeError:
            _logger.warning("Claude feedback JSON invalide: %s", raw[:300])
        return {
            "analysis": (raw or "")[:500],
            "weaknesses": [],
            "prompt_suggestions": [],
        }
