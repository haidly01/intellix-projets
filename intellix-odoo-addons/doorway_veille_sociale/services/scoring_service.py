# -*- coding: utf-8 -*-
"""Scoring batch des signaux veille — 1 appel Claude pour N signaux."""
import json
import logging

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.doorway_agents_dashboard.services.claude_service import ClaudeService
except ImportError:
    ClaudeService = None

BATCH_SYSTEM = (
    "Tu analyses des signaux web pour une agence de rénovation/chauffage au Québec. "
    "Réponds UNIQUEMENT en JSON valide."
)


class VeilleScoringService:
    """Batch scoring via Haiku."""

    def __init__(self, env):
        self.env = env
        self.claude_service = ClaudeService(env) if ClaudeService else None

    def _claude_available(self):
        if self.claude_service and self.claude_service.is_available():
            return True
        try:
            return self.env["renovation.ai.service"].sudo()._available()
        except KeyError:
            return False

    def _call_claude_json(self, system_prompt, user_content, max_tokens=1000):
        """Appel Claude avec repli sur renovation.ai.service."""
        if self.claude_service and self.claude_service.is_available():
            payload = self.claude_service.build_messages_payload(
                "intent_detection",
                system_prompt,
                user_content,
                max_tokens=max_tokens,
                use_cache=True,
            )
            return self.claude_service._call_api(payload)
        ai = self.env["renovation.ai.service"].sudo()
        return ai._call(
            [{"role": "user", "content": user_content}],
            system=system_prompt,
            max_tokens=max_tokens,
            purpose="veille_scoring",
        )

    def score_signals_batch(self, signals, tenant_id=None):
        """
        Score tous les signaux en UN appel Claude (Haiku).
        signals : [{'id': ..., 'content': ..., 'source': ...}, ...]
        """
        if not signals:
            return []
        if not self._claude_available():
            return [{"id": s["id"], "score": 5, "intent": "unknown", "pipeline": "renovation"} for s in signals]

        signals_text = "\n---\n".join(
            [
                "ID: %s\nSource: %s\nContenu: %s"
                % (s.get("id"), s.get("source", ""), (s.get("content") or "")[:500])
                for s in signals
            ]
        )
        user_content = f"""
Analyse ces {len(signals)} signaux pour une agence de rénovation/chauffage au Québec.

SIGNAUX :
{signals_text}

RÉPONSE FORMAT JSON UNIQUEMENT :
{{
  "scores": [
    {{
      "id": "id_du_signal",
      "score": 8,
      "intent": "achat",
      "pipeline": "renovation",
      "urgent": true,
      "reason": "1 phrase max"
    }}
  ]
}}
"""
        try:
            raw = self._call_claude_json(BATCH_SYSTEM, user_content, max_tokens=1000)
            if tenant_id:
                try:
                    from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

                    CreditEngine(self.env).debit_service(
                        tenant_id, "claude_analysis", quantity=1
                    )
                except ImportError:
                    pass
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw[start:end])
                return result.get("scores") or []
        except (json.JSONDecodeError, TypeError) as error:
            _logger.warning("Batch scoring JSON invalide : %s", error)
        return [{"id": s["id"], "score": 5} for s in signals]

    def apply_scores_to_records(self, signal_records):
        """Score un recordset doorway.veille.signal et met à jour les champs."""
        batch = []
        for rec in signal_records:
            batch.append(
                {
                    "id": str(rec.id),
                    "content": rec.texte or rec.titre or "",
                    "source": rec.source or rec.plateforme or "",
                }
            )
        tenant_id = self.env.company.id
        scores = self.score_signals_batch(batch, tenant_id=tenant_id)
        score_by_id = {str(s.get("id")): s for s in scores}
        for rec in signal_records:
            data = score_by_id.get(str(rec.id)) or {}
            score = int(data.get("score") or 5)
            temp = "cold"
            if score >= 8:
                temp = "hot"
            elif score >= 4:
                temp = "warm"
            rec.sudo().write(
                {
                    "score_intention": score,
                    "score_final": score,
                    "temperature": temp,
                    "resume": (data.get("reason") or rec.resume)[:100],
                    "type_projet": data.get("pipeline") or rec.type_projet,
                }
            )
            if temp == "hot":
                rec._notify_hot()
        try:
            from odoo.addons.doorway_veille_sociale.services.lead_copy import (
                apply_lead_copy_to_records,
            )

            try:
                from odoo.addons.doorway_social_ia.controllers.veille_dash_api import (
                    infer_branche,
                )
            except Exception as import_err:  # noqa: BLE001
                _logger.warning("lead_copy infer_branche fallback: %s", import_err)

                def infer_branche(sig):
                    return (getattr(sig, "plateforme", None) or "") or "non_pertinent"

            apply_lead_copy_to_records(self, signal_records, infer_branche)
        except Exception as err:  # noqa: BLE001
            _logger.warning("lead_copy after score failed: %s", err)
            for rec in signal_records:
                if (rec.reponse_publique or "").strip() and (rec.message_prive or "").strip():
                    continue
                rec.sudo().write(
                    {
                        "reponse_publique": rec.reponse_publique
                        or "[Génération échouée] %s — relance depuis le tiroir." % err,
                        "message_prive": rec.message_prive
                        or "[Génération échouée] Relance « Régénérer la réponse ».",
                    }
                )
        return len(scores)
