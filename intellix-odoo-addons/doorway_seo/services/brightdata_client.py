# -*- coding: utf-8 -*-
"""Client Bright Data — OPTIONNEL et best-effort.

Sert à enrichir, jamais à bloquer :
  - ``serp_search`` : requête SERP (découverte de cibles / vérification de
    citations) via l'API Bright Data si une zone SERP est configurée.

Si Bright Data n'est pas configuré OU si l'appel échoue, on renvoie
``(None, message)`` et l'appelant continue sans dégradation fonctionnelle
(Claude fonctionne seul). Ne lève jamais.
"""
import json
import logging

import requests

from . import config_loader

_logger = logging.getLogger(__name__)

BRIGHTDATA_URL = "https://api.brightdata.com/request"
TIMEOUT = 30


def is_available(env):
    return config_loader.brightdata_available(env)


def serp_search(env, query, country="ca", num=10):
    """Retourne (results | None, message).

    ``results`` est une liste de dicts {title, url, snippet} extraits du SERP
    Google. Best-effort : tout échec renvoie (None, message) sans lever.
    """
    cfg = config_loader.get_brightdata_config(env)
    if not cfg:
        return None, "Bright Data non configuré (optionnel)."
    try:
        from urllib.parse import quote_plus

        target = (
            "https://www.google.com/search?q=%s&num=%d&gl=%s&brd_json=1"
            % (quote_plus(query), int(num), country)
        )
        payload = {"zone": cfg["zone"], "url": target, "format": "raw"}
        headers = {
            "Authorization": "Bearer %s" % cfg["api_key"],
            "Content-Type": "application/json",
        }
        resp = requests.post(
            BRIGHTDATA_URL, headers=headers, data=json.dumps(payload), timeout=TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001
        _logger.info("Bright Data SERP injoignable : %s", exc)
        return None, "Bright Data injoignable (ignoré)."

    if resp.status_code != 200:
        _logger.info("Bright Data SERP HTTP %s", resp.status_code)
        return None, "Bright Data a renvoyé HTTP %s (ignoré)." % resp.status_code

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None, "Réponse Bright Data illisible (ignoré)."

    organic = data.get("organic") or data.get("organic_results") or []
    results = []
    for item in organic[: int(num)]:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("link") or item.get("url") or "",
                "snippet": item.get("description") or item.get("snippet") or "",
            }
        )
    if not results:
        return None, "Aucun résultat SERP exploitable (ignoré)."
    return results, "%d résultat(s) SERP." % len(results)


def _request_serp_json(env, target):
    """Appel Bright Data brut renvoyant le JSON SERP analysé, ou (None, msg)."""
    cfg = config_loader.get_brightdata_config(env)
    if not cfg:
        return None, "Bright Data SERP non configuré."
    try:
        payload = {"zone": cfg["zone"], "url": target, "format": "raw"}
        headers = {
            "Authorization": "Bearer %s" % cfg["api_key"],
            "Content-Type": "application/json",
        }
        resp = requests.post(
            BRIGHTDATA_URL, headers=headers, data=json.dumps(payload), timeout=TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001
        _logger.info("Bright Data SERP injoignable : %s", exc)
        return None, "Bright Data injoignable (ignoré)."
    if resp.status_code != 200:
        _logger.info("Bright Data SERP HTTP %s", resp.status_code)
        return None, "Bright Data a renvoyé HTTP %s (ignoré)." % resp.status_code
    try:
        return resp.json(), "OK"
    except Exception:  # noqa: BLE001
        return None, "Réponse Bright Data illisible (ignoré)."


def serp_full(env, query, country="ca", lang="fr", num=20):
    """Retourne (serp_dict | None, message).

    ``serp_dict`` normalisé et défensif :
        {
          "organic":   [{"position": int, "title": str, "url": str, "domain": str}],
          "related":   [str, ...],          # recherches associées
          "paa":       [str, ...],          # People Also Ask
          "features":  [str, ...],          # éléments SERP repérés
        }
    Tout échec / absence de config → (None, message). Ne lève jamais.
    """
    from urllib.parse import quote_plus

    target = (
        "https://www.google.com/search?q=%s&num=%d&gl=%s&hl=%s&brd_json=1"
        % (quote_plus(query or ""), int(num), country or "ca", lang or "fr")
    )
    data, msg = _request_serp_json(env, target)
    if data is None:
        return None, msg
    if not isinstance(data, dict):
        return None, "SERP Bright Data inattendu (ignoré)."

    organic_raw = data.get("organic") or data.get("organic_results") or []
    organic = []
    if isinstance(organic_raw, list):
        for idx, item in enumerate(organic_raw):
            if not isinstance(item, dict):
                continue
            url = item.get("link") or item.get("url") or ""
            try:
                pos = int(item.get("rank") or item.get("position") or (idx + 1))
            except (TypeError, ValueError):
                pos = idx + 1
            organic.append(
                {
                    "position": pos,
                    "title": item.get("title") or "",
                    "url": url,
                    "domain": _domain_of(url),
                }
            )

    related = _string_list(
        data.get("related") or data.get("related_searches") or data.get("related_searches_list")
    )
    paa = _paa_list(data.get("people_also_ask") or data.get("related_questions") or data.get("paa"))

    features = []
    for key, label in (
        ("featured_snippet", "Featured snippet"),
        ("answer_box", "Answer box"),
        ("knowledge", "Knowledge panel"),
        ("local_results", "Local pack"),
        ("local_pack", "Local pack"),
        ("images", "Images"),
        ("videos", "Vidéos"),
        ("shopping", "Shopping"),
        ("top_ads", "Annonces"),
        ("ads", "Annonces"),
    ):
        if data.get(key):
            if label not in features:
                features.append(label)
    if paa and "People Also Ask" not in features:
        features.append("People Also Ask")

    serp = {"organic": organic, "related": related, "paa": paa, "features": features}
    if not organic and not related and not paa:
        return None, "SERP vide ou non analysable (ignoré)."
    return serp, "SERP récupéré (%d résultats organiques)." % len(organic)


def autocomplete(env, query, country="ca", lang="fr"):
    """Suggestions d'autocomplétion Google via Bright Data. (list | None, msg)."""
    cfg = config_loader.get_brightdata_config(env)
    if not cfg:
        return None, "Bright Data non configuré (autocomplete ignoré)."
    from urllib.parse import quote_plus

    target = (
        "https://suggestqueries.google.com/complete/search?client=firefox&hl=%s&gl=%s&q=%s"
        % (lang or "fr", country or "ca", quote_plus(query or ""))
    )
    try:
        payload = {"zone": cfg["zone"], "url": target, "format": "raw"}
        headers = {
            "Authorization": "Bearer %s" % cfg["api_key"],
            "Content-Type": "application/json",
        }
        resp = requests.post(
            BRIGHTDATA_URL, headers=headers, data=json.dumps(payload), timeout=TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001
        _logger.info("Autocomplete injoignable : %s", exc)
        return None, "Autocomplete injoignable (ignoré)."
    if resp.status_code != 200:
        return None, "Autocomplete HTTP %s (ignoré)." % resp.status_code
    try:
        parsed = resp.json()
    except Exception:  # noqa: BLE001
        return None, "Autocomplete illisible (ignoré)."
    # Format Google suggest : [query, [suggestions...], ...]
    if isinstance(parsed, list) and len(parsed) >= 2 and isinstance(parsed[1], list):
        sugg = [s for s in parsed[1] if isinstance(s, str) and s.strip()]
        if sugg:
            return sugg, "%d suggestion(s)." % len(sugg)
    return None, "Aucune suggestion exploitable (ignoré)."


# ----------------------------------------------------------------------------
# Helpers internes (purs)
# ----------------------------------------------------------------------------
def _domain_of(url):
    try:
        from urllib.parse import urlparse

        host = urlparse(url if "://" in (url or "") else "http://" + (url or "")).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


def _string_list(value):
    out = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                txt = item.get("query") or item.get("title") or item.get("text") or ""
                if txt:
                    out.append(txt.strip())
    return out


def _paa_list(value):
    out = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                txt = item.get("question") or item.get("title") or item.get("text") or ""
                if txt:
                    out.append(txt.strip())
    return out
