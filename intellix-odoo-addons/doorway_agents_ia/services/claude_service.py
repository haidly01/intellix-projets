# -*- coding: utf-8 -*-
"""Analyse Claude (temps réel + post-appel) — optimisé coûts (Haiku + cache + delta)."""
import json
import logging

import requests

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
PROMPT_CACHING_BETA = "prompt-caching-2024-07-31"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

HAIKU_TASKS = frozenset(
    {
        "realtime_analysis",
        "lead_scoring",
        "intent_detection",
        "call_summary_short",
        "lead_classification",
        "email_followup",
        "sentiment_analysis",
    }
)
SONNET_TASKS = frozenset(
    {
        "post_call_report",
        "live_coaching",
        "complex_analysis",
        "objection_handling",
    }
)

AGENT_COACHING_SYSTEM_PROMPT = (
    "Tu es un coach commercial senior pour l'Agence Doorway (Québec). "
    "Réponds en français, 1-2 phrases max : quoi de nouveau et action requise."
)


class ClaudeService:
    """Appels API Anthropic pour coaching et scoring."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _config(self):
        key = self._icp.get_param("doorway_agents_ia.anthropic_api_key") or self._icp.get_param(
            "renovation_conciergerie.anthropic_api_key", ""
        )
        return {"api_key": key}

    def is_available(self):
        return bool(self._config()["api_key"])

    def get_model_for_task(self, task_type):
        """
        Sélectionne le modèle Claude selon la complexité de la tâche.
        Haiku = ~20x moins cher que Sonnet, suffisant pour 80% des tâches.
        """
        if task_type in HAIKU_TASKS:
            return HAIKU_MODEL
        if task_type in SONNET_TASKS:
            return SONNET_MODEL
        override = self._icp.get_param("doorway_agents_ia.anthropic_model")
        if override and override not in ("claude-sonnet-4-20250514",):
            return override
        return SONNET_MODEL

    def build_messages_payload(
        self, task_type, system_prompt, user_content, max_tokens=1000, use_cache=True
    ):
        """
        Construit le payload Messages API avec cache éphemère sur le system prompt.
        Économie : ~90% sur les tokens system après le 1er appel.
        """
        system = system_prompt
        if use_cache and system_prompt:
            system = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        return {
            "model": self.get_model_for_task(task_type),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
        }

    def _call_api(self, payload):
        """Exécute l'appel HTTP Anthropic. Renvoie le texte brut."""
        cfg = self._config()
        if not cfg["api_key"]:
            return ""
        headers = {
            "x-api-key": cfg["api_key"],
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        if isinstance(payload.get("system"), list):
            headers["anthropic-beta"] = PROMPT_CACHING_BETA
        try:
            resp = requests.post(
                ANTHROPIC_URL, headers=headers, data=json.dumps(payload), timeout=60
            )
            if resp.status_code != 200:
                _logger.warning("Claude HTTP %s : %s", resp.status_code, resp.text[:200])
                return ""
            data = resp.json()
            parts = data.get("content") or []
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        except Exception as error:  # noqa: BLE001
            _logger.warning("Claude API : %s", error)
            return ""

    def analyze(self, content, task_type, system_prompt=None):
        """Point d'entrée générique (utilisé par credit_engine / veille)."""
        system = system_prompt or "Tu es un assistant pour l'Agence Doorway (Québec). Réponds en français."
        payload = self.build_messages_payload(
            task_type,
            system,
            content or "",
            max_tokens=800,
            use_cache=bool(system_prompt),
        )
        return self._call_api(payload)

    def _extract_last_segment(self, transcript, seconds=30):
        """Extrait les N dernières secondes du transcript (~10 dernières lignes)."""
        if not transcript:
            return ""
        lines = [ln for ln in transcript.split("\n") if ln.strip()]
        recent_lines = lines[-10:]
        return "\n".join(recent_lines)

    def _tenant_id_for_credits(self):
        """Résout le tenant SaaS lié à la société courante."""
        Tenant = self.env.get("doorway.tenant")
        if not Tenant:
            return None
        tenant = Tenant.get_tenant_for_company()
        return tenant.id if tenant else None

    def _guard_credits(self, service, quantity=1):
        """Vérifie le solde AVANT appel API externe."""
        tenant_id = self._tenant_id_for_credits()
        if not tenant_id:
            return True, None
        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        check = CreditEngine(self.env).check_balance(tenant_id, service, quantity)
        if not check["can_proceed"]:
            return False, check
        return True, tenant_id

    def _debit_credits(self, service, tenant_id, call_id=None, description=""):
        """Débite après succès API."""
        if not tenant_id:
            return
        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        CreditEngine(self.env).debit_service(
            tenant_id, service, call_id=call_id, description=description
        )

    def analyze_call_realtime(
        self, full_transcript, previous_analysis=None, agent_prompt="", call_id=None
    ):
        """
        N'envoie que le delta (~30 s) du transcript, pas l'appel entier.
        Modèle : Haiku (realtime_analysis).
        """
        ok, credit_ctx = self._guard_credits("claude_analysis")
        if not ok:
            return {
                "error": "insufficient_credits",
                "balance": credit_ctx.get("balance"),
            }
        tenant_id = credit_ctx

        previous_analysis = previous_analysis or {}
        last_segment = self._extract_last_segment(full_transcript, seconds=30)
        if not last_segment:
            return ""

        system = AGENT_COACHING_SYSTEM_PROMPT
        if agent_prompt:
            system += "\n\nScript agent (référence) :\n" + agent_prompt[:1500]

        user_content = (
            "Nouvelles 30 secondes :\n"
            f"{last_segment}\n\n"
            f"Analyse précédente (résumé) : {previous_analysis.get('summary', 'Début d appel')}\n\n"
            "En 1-2 phrases max : quoi de nouveau? Action requise?"
        )
        payload = self.build_messages_payload(
            "realtime_analysis",
            system,
            user_content,
            max_tokens=400,
            use_cache=True,
        )
        text = self._call_api(payload)
        if text and tenant_id:
            self._debit_credits(
                "claude_analysis",
                tenant_id,
                call_id=call_id,
                description="Analyse temps réel",
            )
        return text

    def analyze_realtime(self, transcript_partial, agent_prompt="", previous_analysis=None):
        """Alias rétrocompatible — délègue à analyze_call_realtime (delta)."""
        prev = previous_analysis
        if prev is None and transcript_partial:
            prev = {"summary": "Début d appel"}
        return self.analyze_call_realtime(
            transcript_partial or "",
            previous_analysis=prev,
            agent_prompt=agent_prompt,
        )

    def analyze_post_call(self, transcript, agent_prompt="", call_id=None):
        """Rapport complet 5 scores — Sonnet (post_call_report)."""
        ok, credit_ctx = self._guard_credits("claude_report")
        if not ok:
            return {
                "error": "insufficient_credits",
                "balance": credit_ctx.get("balance"),
            }
        tenant_id = credit_ctx

        system = (
            "Tu es évaluateur QA pour Agence Doorway. Réponds UNIQUEMENT en JSON valide avec les clés : "
            "score_accroche, score_qualification, score_objections, score_closing, score_global "
            "(float 0-10), points_forts, points_amelioration, prochaine_action "
            "(rappel|email|rdv|archiver), claude_summary."
        )
        if agent_prompt:
            system += "\nScript : " + agent_prompt[:1500]
        payload = self.build_messages_payload(
            "post_call_report",
            system,
            "Transcript complet :\n" + (transcript or "")[:12000],
            max_tokens=1200,
            use_cache=True,
        )
        raw = self._call_api(payload)
        if tenant_id and raw:
            self._debit_credits(
                "claude_report", tenant_id, call_id=call_id, description="Rapport post-appel"
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
