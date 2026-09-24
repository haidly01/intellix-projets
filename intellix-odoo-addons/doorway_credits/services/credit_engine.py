# -*- coding: utf-8 -*-
"""Moteur de crédits IA — débit, cache et règles zéro-IA."""
import hashlib
import logging
import time

_logger = logging.getLogger(__name__)


class CreditEngine:
    """Point d'entrée unique pour débit / vérification de crédits."""

    _analysis_cache = {}
    CACHE_TTL = 3600

    def __init__(self, env):
        self.env = env

    def _resolve_tenant(self, tenant_id=None):
        if tenant_id:
            return self.env["doorway.tenant"].sudo().browse(int(tenant_id))
        return self.env["doorway.tenant"].get_tenant_for_company()

    def get_service_price(self, service, quantity=1, tenant_id=None):
        """Prix client pour un service (grille globale ou tarif tenant demo)."""
        tenant = self._resolve_tenant(tenant_id)
        if tenant:
            custom = tenant._doorway_custom_service_price(service, quantity)
            if custom is not None:
                return custom
        pricing = self.env["doorway.ai.pricing"].get_pricing(service)
        return round(pricing["client_price"] * quantity, 2)

    def check_balance(self, tenant_id, service, quantity=1):
        """
        Vérifie si le tenant peut consommer sans débiter.
        Retourne {can_proceed, balance, required}.
        """
        tenant = self._resolve_tenant(tenant_id)
        if not tenant or not tenant.credit_account_id:
            return {"can_proceed": True, "balance": 0.0, "required": 0.0, "reason": "no_tenant"}
        if tenant.status not in ("trial", "active"):
            return {
                "can_proceed": False,
                "balance": tenant.credit_balance,
                "required": self.get_service_price(
                    service, quantity, tenant_id=tenant.id
                ),
                "reason": "inactive",
            }
        required = self.get_service_price(service, quantity, tenant_id=tenant.id)
        account = tenant.credit_account_id
        daily_ok = account.today_consumption + required <= tenant.daily_credit_limit
        balance_ok = tenant.credit_balance >= required
        return {
            "can_proceed": balance_ok and daily_ok,
            "balance": tenant.credit_balance,
            "required": required,
            "reason": "insufficient_balance" if not balance_ok else ("daily_limit" if not daily_ok else "ok"),
        }

    def debit_service(
        self,
        tenant_id,
        service,
        quantity=1,
        call_id=None,
        description=None,
        skip_debit=False,
    ):
        """
        Débite des crédits après consommation IA.
        Retourne {success, balance_after, transaction_id, reason}.
        """
        if skip_debit:
            return {"success": True, "balance_after": 0.0, "reason": "skipped"}

        tenant = self._resolve_tenant(tenant_id)
        if not tenant or not tenant.credit_account_id:
            return {"success": True, "balance_after": 0.0, "reason": "no_tenant"}

        check = self.check_balance(tenant.id, service, quantity)
        if not check["can_proceed"]:
            return {
                "success": False,
                "balance_after": check["balance"],
                "reason": check.get("reason", "insufficient_balance"),
            }

        amount = check["required"]
        desc = description or "Consommation %s" % service
        session_id = False
        if call_id:
            session = self.env["doorway.call.session"].sudo().search(
                [("twilio_call_sid", "=", call_id)], limit=1
            )
            if not session:
                try:
                    session = self.env["doorway.call.session"].sudo().browse(int(call_id))
                except (TypeError, ValueError):
                    session = self.env["doorway.call.session"]
            if session and session.exists():
                session_id = session.id

        tx = tenant.credit_account_id.debit(
            amount,
            service,
            desc,
            call_session_id=session_id or False,
        )
        if not tx:
            return {"success": False, "balance_after": tenant.credit_balance, "reason": "debit_failed"}
        return {
            "success": True,
            "balance_after": tenant.credit_balance,
            "transaction_id": tx.id,
        }

    def should_use_ai(self, lead_data, task_type):
        """Règles déterministes — 0 coût IA si applicable."""
        lead_data = lead_data or {}
        if task_type == "lead_scoring":
            score = 5
            if lead_data.get("budget", 0) > 10000:
                score += 3
            if lead_data.get("timeline") == "immediate":
                score += 2
            if lead_data.get("phone_verified"):
                score += 1
            if lead_data.get("email_verified"):
                score += 1
            if lead_data.get("previous_client"):
                score += 2
            if score >= 9 or score <= 3:
                return {"use_ai": False, "score": min(score, 10)}
        if task_type == "intent_detection":
            content = (lead_data.get("content") or "").lower()
            high = ["prix", "soumission", "combien", "disponible", "urgent", "dès que possible"]
            low = ["juste curieux", "pas pressé", "dans 2 ans", "peut-être"]
            if any(kw in content for kw in high):
                return {"use_ai": False, "intent": "high", "score": 8}
            if any(kw in content for kw in low):
                return {"use_ai": False, "intent": "low", "score": 3}
        return {"use_ai": True}

    def analyze_with_cache(self, content, task_type, tenant_id, lead_data=None):
        """Cache + heuristiques + Claude (débit si appel API)."""
        from odoo.addons.doorway_agents_dashboard.services.claude_service import ClaudeService

        heuristic = self.should_use_ai(lead_data, task_type)
        if not heuristic.get("use_ai", True):
            return heuristic

        cache_key = hashlib.md5(f"{task_type}:{content}".encode()).hexdigest()
        cached = self._analysis_cache.get(cache_key)
        if cached and time.time() - cached["timestamp"] < self.CACHE_TTL:
            return cached["result"]

        check = self.check_balance(tenant_id, "claude_analysis")
        if not check["can_proceed"]:
            return {"error": "insufficient_credits", "balance": check["balance"]}

        result = ClaudeService(self.env).analyze(content, task_type)
        self._analysis_cache[cache_key] = {"result": result, "timestamp": time.time()}
        self.debit_service(tenant_id, "claude_analysis", description="Analyse %s" % task_type)
        return result

    def send_low_balance_alert(self, tenant):
        tenant._check_low_balance_alert()

    def debit_sofia_es_call(self, tenant_id, call_data):
        """
        Facture un appel Sofia Espagne (0.22€/min à la seconde, 0€ si AMD).
        call_data: call_sid, duration_seconds, amd_result, partner_id?, campaign?
        """
        from odoo.addons.doorway_credits.services.sofia_es_billing import compute_sofia_es_cost

        call_data = call_data or {}
        billing = compute_sofia_es_cost(
            call_data.get("duration_seconds"),
            call_data.get("amd_result"),
        )
        call_sid = call_data.get("call_sid") or ""
        campaign = call_data.get("campaign") or "sofia_es_avatrade"
        desc = "Sofia ES — %s — %ss — AMD:%s" % (
            call_sid,
            billing["duration_seconds"],
            billing["amd_result"],
        )

        tenant = self._resolve_tenant(tenant_id)
        if not tenant or not tenant.credit_account_id:
            return {
                "success": True,
                "billed": billing["billed"],
                "cost_euros": billing["cost_euros"],
                "reason": "no_tenant",
                **billing,
            }

        tx_extra = {
            "call_sid": call_sid,
            "duration_seconds": billing["duration_seconds"],
            "cost_euros": billing["cost_euros"],
            "amd_result": billing["amd_result"] if billing["amd_result"] in (
                "human", "machine", "not_sure", "unknown"
            ) else "unknown",
            "campaign_ref": campaign,
        }

        if not billing["billed"] or billing["cost_euros"] <= 0:
            tx = tenant.credit_account_id.env["doorway.credit.transaction"].sudo().create(
                {
                    "account_id": tenant.credit_account_id.id,
                    "transaction_type": "consumption",
                    "service": "sofia_es_call",
                    "amount": 0.0,
                    "balance_after": tenant.credit_balance,
                    "description": desc + " (non facturé)",
                    **tx_extra,
                }
            )
            return {
                "success": True,
                "billed": False,
                "transaction_id": tx.id,
                "balance_after": tenant.credit_balance,
                **billing,
            }

        amount_usd = billing["cost_euros"]
        check = self.check_balance(tenant.id, "sofia_es_call", billing["duration_seconds"] / 60.0)
        if not check["can_proceed"]:
            amount_usd = min(amount_usd, max(0.0, tenant.credit_balance))

        session_id = False
        if call_sid:
            session = self.env["doorway.call.session"].sudo().search(
                [("twilio_call_sid", "=", call_sid)], limit=1
            )
            if session:
                session_id = session.id

        tx = tenant.credit_account_id.debit(
            amount_usd,
            "sofia_es_call",
            desc,
            call_session_id=session_id or False,
            real_cost=billing["cost_euros"] * 0.5,
            tx_extra=tx_extra,
        )
        if not tx:
            return {
                "success": False,
                "billed": False,
                "balance_after": tenant.credit_balance,
                "reason": "debit_failed",
                **billing,
            }
        return {
            "success": True,
            "billed": True,
            "transaction_id": tx.id,
            "balance_after": tenant.credit_balance,
            **billing,
        }

    def get_consumption_report(self, tenant_id, date_from, date_to):
        """Rapport de consommation par service."""
        tenant = self._resolve_tenant(tenant_id)
        if not tenant:
            return []
        domain = [
            ("tenant_id", "=", tenant.id),
            ("transaction_type", "=", "consumption"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        txs = self.env["doorway.credit.transaction"].read_group(
            domain,
            ["service", "amount:sum", "charged_amount:sum"],
            ["service"],
        )
        return txs
