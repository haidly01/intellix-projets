# -*- coding: utf-8 -*-
import json
import logging
import re
from html import escape

from odoo import _, api, models

_logger = logging.getLogger(__name__)

DEFAULT_SYSTEM = (
    "Tu es le Copilot support Intellix (Doorway). "
    "Analyse le ticket et le diagnostic JSON fournis. "
    "Réponds en français, concis et actionnable pour un agent support. "
    "Structure : diagnostic probable, causes possibles, actions recommandées "
    "(runbooks Odoo si pertinent : access_denied, calls_not_dialing, lea_silent). "
    "N'invente pas de données absentes du contexte. "
    "Format HTML léger : <p>, <ul><li>, <strong> — pas de markdown."
)

PROMPT_CODE = "intellix_support_copilot"


class IntellixSupportCopilotLlm(models.AbstractModel):
    _name = "intellix.support.copilot.llm"
    _description = "Copilot support — appels LLM Claude"

    @api.model
    def _ai_available(self):
        if "renovation.ai.service" not in self.env:
            return False
        return self.env["renovation.ai.service"]._available()

    @api.model
    def _call_ai(self, user_content, system=None, purpose="intellix_support_copilot", max_tokens=2048):
        if not self._ai_available():
            return None
        system_prompt = system
        if system_prompt is None:
            if "renovation.ai.service" in self.env:
                system_prompt = self.env["renovation.ai.service"]._get_prompt(
                    PROMPT_CODE, DEFAULT_SYSTEM
                )
            else:
                system_prompt = DEFAULT_SYSTEM
        try:
            return self.env["renovation.ai.service"]._call(
                [{"role": "user", "content": user_content}],
                system=system_prompt,
                max_tokens=max_tokens,
                purpose=purpose,
            )
        except Exception as exc:
            _logger.exception("Support Copilot LLM call failed")
            return None

    @api.model
    def _strip_html(self, html):
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html or "")
        return re.sub(r"\s+", " ", text).strip()

    @api.model
    def _build_context(self, ticket, question):
        ticket.ensure_one()
        checks = []
        if ticket.last_diagnostic_id and ticket.last_diagnostic_id.result_json:
            try:
                checks = json.loads(ticket.last_diagnostic_id.result_json)
            except (TypeError, ValueError):
                checks = []

        runbook_hint = ""
        Runbook = self.env.get("intellix.support.runbook")
        if Runbook:
            matched = ticket._copilot_match_runbook()
            if matched:
                runbook_hint = f"{matched.code} ({matched.name}, phase={matched.phase})"

        payload = {
            "ticket": {
                "ref": ticket.name,
                "subject": ticket.subject or "",
                "description": self._strip_html(ticket.description),
                "category": ticket.category_id.code if ticket.category_id else "",
                "side_origin": ticket.side_origin,
                "partner": ticket.partner_id.display_name if ticket.partner_id else "",
                "contact_user": ticket.contact_user_id.login if ticket.contact_user_id else "",
                "copilot_summary": ticket.copilot_summary or "",
            },
            "diagnostic": {
                "checks": checks,
                "passed": ticket.last_diagnostic_id.checks_passed if ticket.last_diagnostic_id else 0,
                "warnings": ticket.last_diagnostic_id.checks_warning if ticket.last_diagnostic_id else 0,
                "failed": ticket.last_diagnostic_id.checks_failed if ticket.last_diagnostic_id else 0,
            },
            "runbook_suggested": runbook_hint,
            "question": question,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @api.model
    def _sanitize_html_answer(self, text):
        text = (text or "").strip()
        if not text:
            return f"<p>{escape(_('Réponse vide.'))}</p>"
        if text.startswith("<"):
            return text
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]
        return "".join(f"<p>{escape(p).replace(chr(10), '<br/>')}</p>" for p in paragraphs)

    @api.model
    def ask(self, ticket, question):
        """Question Copilot — LLM si disponible, sinon règles diagnostic_engine."""
        ticket.ensure_one()
        question = (question or "").strip()
        engine = self.env["intellix.support.diagnostic.engine"]

        if self._ai_available():
            context = self._build_context(ticket, question)
            user_prompt = (
                f"Contexte ticket et diagnostic (JSON):\n{context}\n\n"
                f"Question de l'agent support:\n{question}\n\n"
                "Propose une analyse et des actions concrètes."
            )
            answer = self._call_ai(user_prompt)
            if answer:
                return {
                    "html": self._sanitize_html_answer(answer),
                    "source": "llm",
                }

        return {
            "html": engine._answer_question_rules(ticket, question),
            "source": "rules",
        }
