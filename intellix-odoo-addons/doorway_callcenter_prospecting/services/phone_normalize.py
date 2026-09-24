# -*- coding: utf-8 -*-
"""Normalisation E.164 Maroc (+212) et Tunisie (+216)."""
import re


def normalize_phone_e164(raw, country_code="MA"):
    """Retourne numéro E.164 ou None."""
    country = (country_code or "MA").upper()
    if not raw:
        return None
    try:
        import phonenumbers

        parsed = phonenumbers.parse(str(raw), country)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
    except Exception:  # noqa: BLE001
        pass
    return _normalize_regex(str(raw), country)


def _normalize_regex(raw, country):
    digits = re.sub(r"\D", "", raw or "")
    if country == "MA":
        if digits.startswith("212"):
            digits = digits[3:]
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) == 9 and digits[0] in "567":
            return "+212%s" % digits
        return None
    if country == "TN":
        if digits.startswith("216"):
            digits = digits[3:]
        if len(digits) == 8 and digits[0] in "23459":
            return "+216%s" % digits
        return None
    return None
