# -*- coding: utf-8 -*-
"""Facturation Sofia Espagne — 0.22 EUR/min à la seconde, AMD = 0 EUR."""

SOFIA_ES_RATE_EUR_PER_SEC = 0.22 / 60.0
AMD_NO_BILL = frozenset({"machine", "not_sure", "fax", "amd_hangup"})


def compute_sofia_es_cost(duration_seconds, amd_result=None):
    """Retourne cost_euros, billed (bool), reason."""
    duration = max(0, int(duration_seconds or 0))
    amd = (amd_result or "unknown").lower()
    if amd in AMD_NO_BILL:
        return {
            "cost_euros": 0.0,
            "billed": False,
            "duration_seconds": duration,
            "amd_result": amd,
            "reason": "AMD_DETECTED",
        }
    if duration <= 0:
        return {
            "cost_euros": 0.0,
            "billed": False,
            "duration_seconds": 0,
            "amd_result": amd,
            "reason": "ZERO_DURATION",
        }
    cost = round(duration * SOFIA_ES_RATE_EUR_PER_SEC, 4)
    return {
        "cost_euros": cost,
        "billed": True,
        "duration_seconds": duration,
        "amd_result": amd,
        "reason": "HUMAN_CALL",
    }
