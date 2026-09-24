# -*- coding: utf-8 -*-
import json
import logging
import re
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SESSION_PROMPT_CODES = {
    "praise": "pe_coaching_praise",
    "coaching": "pe_coaching",
    "warning": "pe_coaching_warning",
    "formal_warn": "pe_coaching_warning",
    "pip": "pe_coaching_pip",
    "termination": "pe_coaching_pip",
}

DEFAULT_PROMPTS = {
    "pe_coaching_praise": (
        "Tu es un expert RH bienveillant. Rédige des félicitations personnalisées "
        "en français (Québec ou France selon le contexte). 150-250 mots max. "
        "Réponds en JSON : {\"analysis\":\"...\",\"draft\":\"...\",\"action_plan\":\"\",\"legal_refs\":\"\"}"
    ),
    "pe_coaching": (
        "Tu es un coach RH. Message constructif : faits → impact → actions SMART. "
        "JSON : {\"analysis\":\"...\",\"draft\":\"...\",\"action_plan\":\"...\",\"legal_refs\":\"\"}"
    ),
    "pe_coaching_warning": (
        "Tu rédiges un avertissement professionnel factuel. Brouillon pour révision humaine obligatoire. "
        "JSON : {\"analysis\":\"...\",\"draft\":\"...\",\"action_plan\":\"...\",\"legal_refs\":\"\"}"
    ),
    "pe_coaching_pip": (
        "Tu rédiges un plan d'amélioration (PIP) structuré avec objectifs SMART et délais. "
        "JSON : {\"analysis\":\"...\",\"draft\":\"...\",\"action_plan\":\"...\",\"legal_refs\":\"\"}"
    ),
    "pe_coaching_plan": (
        "Tu rédiges un plan de développement 30/60/90 jours pour un employé. "
        "JSON : {\"title\":\"...\",\"content\":\"<html>\",\"success_criteria\":\"...\",\"risk_factors\":\"...\"}"
    ),
    "pe_call_coaching": (
        "Tu es un coach commercial expert pour agents call center Doorway. "
        "Analyse le transcript et réponds UNIQUEMENT en JSON : score_global (0-100), "
        "score_accroche, score_qualification, score_gestion_objections, score_closing "
        "(chacun 0-25), points_positifs, points_ameliorer, conseil."
    ),
}


class PeopleEngineClaudeCoachingService(models.AbstractModel):
    _name = "pe.claude.coaching.service"
    _description = "Moteur Claude coaching People Engine"

    @api.model
    def _ai_service(self):
        if "renovation.ai.service" not in self.env:
            return None
        return self.env["renovation.ai.service"]

    @api.model
    def _ai_available(self):
        if "renovation.ai.service" not in self.env:
            return False
        return self.env["renovation.ai.service"]._available()

    @api.model
    def _get_prompt(self, code):
        default = DEFAULT_PROMPTS.get(code, DEFAULT_PROMPTS["pe_coaching"])
        if "renovation.ai.service" not in self.env:
            return default
        return self.env["renovation.ai.service"]._get_prompt(code, default)

    @api.model
    def _call_ai(self, user_content, system, purpose, max_tokens=2048):
        if not self._ai_available():
            return None
        try:
            return self.env["renovation.ai.service"]._call(
                [{"role": "user", "content": user_content}],
                system=system,
                max_tokens=max_tokens,
                purpose=purpose,
            )
        except UserError:
            raise
        except Exception as exc:
            _logger.exception("PE Claude coaching")
            return None

    @api.model
    def _parse_json_response(self, text):
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"draft": text, "analysis": "", "action_plan": "", "legal_refs": ""}

    @api.model
    def get_employee_jurisdiction(self, profile):
        emp = profile.employee_id
        partner = emp.work_contact_id or emp.address_id
        country = partner.country_id.code if partner and partner.country_id else "CA"
        if country == "CA":
            state = partner.state_id.code if partner and partner.state_id else "QC"
            return state or "QC"
        return country or "FR"

    @api.model
    def _employee_data(self, profile):
        emp = profile.employee_id
        months = 0
        start_date = False
        contract_type = "CDI"
        Contract = self.env.get("hr.contract")
        if Contract:
            contracts = Contract.search(
                [("employee_id", "=", emp.id)], order="date_start asc", limit=1
            )
            if contracts:
                start_date = contracts.date_start
                contract_type = getattr(contracts, "contract_type", None) or "CDI"
        if not start_date and getattr(emp, "contract_date_start", False):
            start_date = emp.contract_date_start
        if start_date:
            delta = date.today() - start_date
            months = max(0, int(delta.days / 30))
        return {
            "months_employed": months,
            "contract_type": contract_type,
        }

    @api.model
    def check_compliance(self, session):
        if session.session_type not in ("formal_warn", "pip", "termination"):
            return {"can_proceed": True, "blockers": [], "warnings": []}
        jurisdiction = self.get_employee_jurisdiction(session.profile_id)
        return self.env["pe.legal.engine"].check_compliance(
            session.session_type,
            jurisdiction,
            self._employee_data(session.profile_id),
        )

    @api.model
    def _build_metrics_summary(self, profile):
        return f"""
MÉTRIQUES — {profile.employee_id.name}
Score global : {profile.score_global:.1f}/100 (Perf {profile.score_performance:.1f} / Eng {profile.score_engagement:.1f} / Croissance {profile.score_growth:.1f})
Tendance : {profile.score_trend} ({profile.score_trend_percent:+.1f}%)
CRM : leads {profile.crm_leads_assigned}, gagnés {profile.crm_leads_won}, conv. {profile.crm_conversion_rate:.1f}%, revenus {profile.crm_revenue_generated:,.0f}$
Projet : on-time {profile.project_ontime_rate:.1f}%
IA : appels {profile.ia_calls_made}, qualité {profile.ia_avg_quality_score:.1f}/10
"""

    @api.model
    def generate_coaching_message(self, session):
        profile = session.profile_id
        metrics = self._build_metrics_summary(profile)
        legal = ""
        if session.session_type in ("formal_warn", "pip", "termination"):
            jurisdiction = self.get_employee_jurisdiction(profile)
            legal = self.env["pe.legal.engine"].build_legal_context_for_claude(
                session.session_type, jurisdiction, profile
            )
        prompt_code = SESSION_PROMPT_CODES.get(session.session_type, "pe_coaching")
        system = self._get_prompt(prompt_code)
        user_msg = f"""
Employé : {profile.employee_id.name}
Gestionnaire : {session.manager_id.name}
Type : {session.session_type}
Déclencheur : {session.trigger_details or 'Manuel'}

{metrics}

{legal}

Notes : {session.trigger_details or '—'}
"""
        answer = self._call_ai(
            user_msg, system, purpose="pe_coaching_session", max_tokens=2048
        )
        if not answer:
            draft = session.trigger_details or _(
                "Rédigez manuellement le message (IA indisponible)."
            )
            session.write(
                {
                    "claude_draft": draft,
                    "claude_analysis": _("Mode manuel — IA non disponible."),
                    "status": "pending_manager",
                }
            )
            return draft

        data = self._parse_json_response(answer)
        session.write(
            {
                "claude_analysis": data.get("analysis") or "",
                "claude_draft": data.get("draft") or answer,
                "claude_action_plan": data.get("action_plan") or "",
                "claude_legal_refs": data.get("legal_refs") or legal[:2000],
                "claude_generated_at": fields.Datetime.now(),
                "claude_model_used": "renovation.ai.service",
                "status": "pending_manager",
            }
        )
        return session.claude_draft

    @api.model
    def generate_development_plan(self, plan):
        profile = plan.profile_id
        metrics = self._build_metrics_summary(profile)
        system = self._get_prompt("pe_coaching_plan")
        user_msg = f"""
Plan {plan.plan_type} — durée {plan.duration_days} jours
Objectif score cible : {plan.score_target or 'non défini'}

{metrics}
"""
        answer = self._call_ai(user_msg, system, purpose="pe_coaching_plan")
        if not answer:
            return {
                "title": plan.name,
                "content": "<p>%s</p>"
                % _("Plan manuel — complétez les sections (IA indisponible)."),
                "success_criteria": "",
                "risk_factors": "",
            }
        data = self._parse_json_response(answer)
        return {
            "title": data.get("title") or plan.name,
            "content": data.get("content") or data.get("draft") or answer,
            "success_criteria": data.get("success_criteria") or "",
            "risk_factors": data.get("risk_factors") or "",
        }

    @api.model
    def analyze_call_transcript(self, transcript):
        """Analyse un transcript d'appel commercial — retourne scores + feedback."""
        if not (transcript or "").strip():
            return {}
        system = self._get_prompt("pe_call_coaching")
        answer = self._call_ai(
            "Transcript :\n%s" % transcript[:12000],
            system=system,
            purpose="pe_call_coaching",
            max_tokens=1500,
        )
        if not answer:
            return {}
        data = self._parse_json_response(answer)
        return {
            "score_global": int(data.get("score_global") or 0),
            "score_accroche": int(data.get("score_accroche") or 0),
            "score_qualification": int(data.get("score_qualification") or 0),
            "score_gestion_objections": int(
                data.get("score_gestion_objections") or 0
            ),
            "score_closing": int(data.get("score_closing") or 0),
            "points_positifs": data.get("points_positifs") or "",
            "points_ameliorer": data.get("points_ameliorer") or "",
            "conseil": data.get("conseil") or data.get("draft") or "",
        }

    @api.model
    def _debit_credits(self, session, tokens_used):
        try:
            if "doorway.credit.engine" in self.env:
                tenant = self.env["res.company"].browse(
                    session.profile_id.company_id.id
                )
                self.env["doorway.credit.engine"].debit_service(
                    tenant_id=tenant.id,
                    service="claude_coaching",
                    amount=tokens_used * 0.000006,
                    description="Coaching IA — %s" % session.session_type,
                )
        except Exception:
            pass
