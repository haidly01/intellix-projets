#!/usr/bin/env python3
"""Devise des fiches lieu Coins Marocain — affichage uniquement.

Devise de référence : celle stockée sur coins.property.currency_id.
La Casa Ysabella (#19) est en EUR — montants inchangés, pas de conversion FX.
Pas de FX géo silencieux sur les fiches hébergement.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REF_CURRENCY = "EUR"
ALLOWED = ("CAD", "EUR", "MAD", "USD")
FX_NOTE = "taux indicatif, prix confirmé au moment de la réservation"
LS_KEY = "cm_fiche_currency"

# Zone euro + micro-États EUR (Cloudflare CF-IPCountry).
EUROZONE = frozenset(
    {
        "AT",
        "BE",
        "CY",
        "DE",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HR",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PT",
        "SI",
        "SK",
        "MC",
        "AD",
    }
)

# Pays connus mais hors CAD/EUR/MAD → USD (geo réussie).
# Geo échouée (vide, XX, T1, invalide) → devise de référence, pas USD.

_SUFFIX = {
    "CAD": " $ CA",
    "EUR": " €",
    "MAD": " DH",
    "USD": " $ US",
}


def normalize_currency(code: str | None, default: str = REF_CURRENCY) -> str:
    raw = str(code or "").strip().upper()
    if raw in ALLOWED:
        return raw
    return default if default in ALLOWED else REF_CURRENCY


def country_to_currency(country: str | None) -> str | None:
    """None = geo échouée. Sinon CAD / EUR / MAD / USD."""
    cc = str(country or "").strip().upper()
    if len(cc) != 2 or cc in {"XX", "T1"}:
        return None
    if cc == "CA":
        return "CAD"
    if cc == "MA":
        return "MAD"
    if cc in EUROZONE:
        return "EUR"
    return "USD"


def pick_display_currency(
    *,
    override: str | None,
    country: str | None,
    ref: str = REF_CURRENCY,
    hebergement: bool = True,
) -> str:
    ref_c = normalize_currency(ref)
    ov = str(override or "").strip().upper()
    if ov in ALLOWED:
        return ov
    # Hébergement partenaire : devise stockée, pas de CAD/USD selon l'IP.
    if hebergement:
        return ref_c
    geo = country_to_currency(country)
    if geo:
        return geo
    return ref_c


def convert_amount(amount: float, src: str, dest: str, rates: dict) -> float | None:
    src_c = normalize_currency(src)
    dest_c = normalize_currency(dest)
    if src_c == dest_c:
        return float(amount)
    if not rates:
        return None
    rf = float(rates.get(src_c) or 0)
    rt = float(rates.get(dest_c) or 0)
    if rf <= 0 or rt <= 0:
        return None
    return float(amount) * (rt / rf)


def format_amount(amount: float, currency: str, *, approx: bool = False) -> str:
    cur = normalize_currency(currency)
    n = int(round(float(amount)))
    body = f"{n}{_SUFFIX[cur]}"
    return f"≈ {body}" if approx else body


def format_price_label(
    amount: float,
    currency: str,
    *,
    kind: str = "room",
    approx: bool = False,
) -> str:
    if not amount:
        return "Tarif sur demande" if kind == "from" else "Sur devis"
    body = format_amount(amount, currency, approx=approx) + " / nuit"
    if kind == "from":
        return f"À partir de {body}"
    return body


def fx_selector_html(active: str = REF_CURRENCY) -> str:
    on = normalize_currency(active)
    buttons = []
    for code in ALLOWED:
        pressed = "true" if code == on else "false"
        cls = "cm-fiche-fx-btn is-on" if code == on else "cm-fiche-fx-btn"
        buttons.append(
            f'<button type="button" class="{cls}" data-fx="{code}" '
            f'aria-pressed="{pressed}">{code}</button>'
        )
    return (
        '<div class="cm-fiche-fx" id="cmFicheFx">'
        '<div class="cm-fiche-fx-sel" role="group" aria-label="Devise">'
        f"{''.join(buttons)}</div>"
        f'<p class="cm-fiche-fx-note">{FX_NOTE}</p></div>'
    )


def _http_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "CoinsTaux/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_rates(base: str = REF_CURRENCY) -> dict:
    """Taux quotidiens — open.er-api.com (inclut MAD), repli Frankfurter (sans MAD)."""
    base_c = normalize_currency(base)
    try:
        data = _http_json(f"https://open.er-api.com/v6/latest/{base_c}")
        rates = data.get("rates") or {}
        out = {c: float(rates[c]) for c in ALLOWED if c in rates}
        if base_c not in out:
            out[base_c] = 1.0
        if len(out) >= 3:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {
                "base": base_c,
                "date": now[:10],
                "updated_at": now,
                "rates": out,
                "source": "open.er-api.com",
            }
    except Exception:
        pass
    data = _http_json(f"https://api.frankfurter.app/latest?from={base_c}&to=EUR,USD")
    rates = data.get("rates") or {}
    out = {base_c: 1.0}
    for c in ("EUR", "USD"):
        if c in rates:
            out[c] = float(rates[c])
    return {
        "base": base_c,
        "date": str(data.get("date") or ""),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rates": out,
        "source": "frankfurter.app",
    }


def write_taux_json(path: Path, payload: dict | None = None) -> dict:
    data = payload or fetch_rates()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data
