# -*- coding: utf-8 -*-
"""Helpers for HR attestations (French amount in words)."""

from num2words import num2words


def amount_to_words_fr(amount, currency_code="MAD"):
    """Convert a monetary amount to French words (dirhams / centimes)."""
    if amount is None:
        return ""
    amount = round(float(amount), 2)
    units = int(amount)
    cents = int(round((amount - units) * 100))
    currency_labels = {
        "MAD": ("dirham", "dirhams", "centime", "centimes"),
        "EUR": ("euro", "euros", "centime", "centimes"),
        "USD": ("dollar", "dollars", "cent", "cents"),
    }
    unit_s, unit_p, cent_s, cent_p = currency_labels.get(
        currency_code, ("unité", "unités", "centime", "centimes")
    )
    parts = [num2words(units, lang="fr")]
    parts.append(unit_p if units > 1 else unit_s)
    if cents:
        parts.append("et")
        parts.append(num2words(cents, lang="fr"))
        parts.append(cent_p if cents > 1 else cent_s)
    return " ".join(parts)
