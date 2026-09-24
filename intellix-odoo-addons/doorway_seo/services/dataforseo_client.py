# -*- coding: utf-8 -*-
"""Client DataForSEO — fournisseur concret de métriques de mots-clés.

Fournit (données RÉELLES, pas d'estimation) :
  - ``search_volume`` : volume mensuel Google Ads + CPC + concurrence.
  - ``keywords_for_keywords`` : idées de mots-clés associées + métriques.
  - ``bulk_keyword_difficulty`` : difficulté (KD) DataForSEO Labs.

Auth : HTTP Basic base64("<login>:<password>") (paramètres
``doorway_seo.dataforseo_login`` / ``doorway_seo.dataforseo_password``).

⚠️ Le suivi de position / SERP reste géré par ``brightdata_client`` — ce module
ne fait PAS de rank tracking.

Robustesse : timeouts, gestion du code HTTP, du ``status_code`` par tâche
DataForSEO (20000 = OK), résultats vides → dégradation propre. Ne lève jamais.
Un cache mémoire (par jour) évite de re-facturer des requêtes identiques.
"""
import base64
import datetime
import json
import logging

import requests

from . import config_loader

_logger = logging.getLogger(__name__)

BASE_URL = "https://api.dataforseo.com"
TIMEOUT = 60
OK_STATUS = 20000

EP_SEARCH_VOLUME = "/v3/keywords_data/google_ads/search_volume"
EP_KEYWORDS_FOR_KEYWORDS = "/v3/keywords_data/google_ads/keywords_for_keywords"
EP_BULK_KD = "/v3/dataforseo_labs/google/bulk_keyword_difficulty"

# Cache mémoire { cache_key: (jour_iso, valeur) } — évite la re-facturation
# d'appels identiques dans la même journée (process courant).
_CACHE = {}


def is_available(env):
    return config_loader.dataforseo_available(env)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _today():
    return datetime.date.today().isoformat()


def _cache_get(key):
    entry = _CACHE.get(key)
    if entry and entry[0] == _today():
        return entry[1]
    return None


def _cache_set(key, value):
    _CACHE[key] = (_today(), value)


def _auth_header(cfg):
    token = base64.b64encode(
        ("%s:%s" % (cfg["login"], cfg["password"])).encode("utf-8")
    ).decode("ascii")
    return {"Authorization": "Basic %s" % token, "Content-Type": "application/json"}


def location_language(env, geo="", language="fr"):
    """Déduit (location_name, language_name) DataForSEO depuis le geo/langue.

    Surchargé par ``doorway_seo.dataforseo_location`` / ``...language`` si fournis.
    QC → 'Canada' ; FR → 'France' ; langue 'fr' → 'French'.
    """
    cfg = config_loader.get_dataforseo_config(env) or {}
    loc = cfg.get("location") or ""
    lang = cfg.get("language") or ""
    g = (geo or "").lower()
    if not loc:
        if any(t in g for t in ("france", "paris", "lyon", "marseille", "fr ")):
            loc = "France"
        elif any(t in g for t in ("québec", "quebec", "montr", "canada", "qc", "laval", "gatineau")):
            loc = "Canada"
        else:
            loc = "Canada"
    if not lang:
        lang = "French" if (language or "fr").lower().startswith("fr") else "English"
    return loc, lang


def _endpoint(env, base):
    """Renvoie l'URL complète selon le mode ('live' par défaut).

    Le mode 'task' (file d'attente asynchrone) est réservé : on retombe sur
    'live' tant qu'il n'est pas implémenté, pour rester interactif et robuste.
    """
    cfg = config_loader.get_dataforseo_config(env) or {}
    mode = cfg.get("mode") or "live"
    if mode == "task":
        _logger.info("DataForSEO : mode 'task' non implémenté, repli sur 'live'.")
    return BASE_URL + base + "/live"


def _post(env, base, tasks):
    """POST défensif. Renvoie (result_list | None, message)."""
    cfg = config_loader.get_dataforseo_config(env)
    if not cfg:
        return None, "DataForSEO non configuré (login/mot de passe manquants)."
    try:
        resp = requests.post(
            _endpoint(env, base),
            headers=_auth_header(cfg),
            data=json.dumps(tasks),
            timeout=TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.info("DataForSEO injoignable : %s", exc)
        return None, "DataForSEO injoignable (volumes « estimé »)."
    if resp.status_code == 401:
        return None, "DataForSEO : identifiants invalides (configurer login/mot de passe)."
    if resp.status_code != 200:
        _logger.info("DataForSEO HTTP %s : %s", resp.status_code, resp.text[:300])
        return None, "DataForSEO a renvoyé HTTP %s (volumes « estimé »)." % resp.status_code
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None, "Réponse DataForSEO illisible."
    # Statut global puis statut par tâche (20000 = OK).
    if isinstance(data, dict) and data.get("status_code") not in (None, OK_STATUS):
        _logger.info("DataForSEO status %s : %s", data.get("status_code"), data.get("status_message"))
    tasks_out = (data or {}).get("tasks") or []
    results = []
    for task in tasks_out:
        if not isinstance(task, dict):
            continue
        if task.get("status_code") != OK_STATUS:
            _logger.info(
                "DataForSEO tâche %s : %s", task.get("status_code"), task.get("status_message")
            )
            continue
        for res in task.get("result") or []:
            if isinstance(res, dict):
                results.append(res)
    if not results:
        return None, "DataForSEO : aucun résultat exploitable."
    return results, "OK"


def _norm_competition(value):
    if isinstance(value, str):
        return value.upper()
    return ""


# ----------------------------------------------------------------------------
# API publique
# ----------------------------------------------------------------------------
def search_volume(env, keywords, geo="", language="fr"):
    """Volume mensuel + CPC + concurrence. Renvoie (dict | None, message).

    dict = { keyword: {volume:int|None, cpc:float|None, competition:str} }
    """
    keywords = [k for k in (keywords or []) if isinstance(k, str) and k.strip()]
    if not keywords:
        return {}, "Aucun mot-clé."
    loc, lang = location_language(env, geo, language)
    ckey = ("sv", loc, lang, tuple(sorted({k.lower() for k in keywords})))
    cached = _cache_get(ckey)
    if cached is not None:
        return cached, "OK (cache)."
    tasks = [{"keywords": keywords[:1000], "location_name": loc, "language_name": lang}]
    results, msg = _post(env, EP_SEARCH_VOLUME, tasks)
    if results is None:
        return None, msg
    out = {}
    for res in results:
        kw = res.get("keyword")
        if not kw:
            continue
        sv = res.get("search_volume")
        out[kw] = {
            "volume": int(sv) if isinstance(sv, (int, float)) else None,
            "cpc": float(res["cpc"]) if isinstance(res.get("cpc"), (int, float)) else None,
            "competition": _norm_competition(res.get("competition")),
        }
    _cache_set(ckey, out)
    return out, "OK"


def bulk_keyword_difficulty(env, keywords, geo="", language="fr"):
    """Difficulté (KD 0-100) DataForSEO Labs. Renvoie (dict | None, message).

    dict = { keyword: difficulty:int }
    """
    keywords = [k for k in (keywords or []) if isinstance(k, str) and k.strip()]
    if not keywords:
        return {}, "Aucun mot-clé."
    loc, lang = location_language(env, geo, language)
    ckey = ("kd", loc, lang, tuple(sorted({k.lower() for k in keywords})))
    cached = _cache_get(ckey)
    if cached is not None:
        return cached, "OK (cache)."
    tasks = [{"keywords": keywords[:1000], "location_name": loc, "language_name": lang}]
    results, msg = _post(env, EP_BULK_KD, tasks)
    if results is None:
        return None, msg
    out = {}
    for res in results:
        for item in res.get("items") or [res]:
            if not isinstance(item, dict):
                continue
            kw = item.get("keyword")
            kd = item.get("keyword_difficulty")
            if kw and isinstance(kd, (int, float)):
                out[kw] = int(kd)
    _cache_set(ckey, out)
    return out, "OK"


def keywords_for_keywords(env, seed, geo="", language="fr", limit=30):
    """Idées de mots-clés associées + métriques. Renvoie (list | None, message).

    list = [{keyword, volume, cpc, competition}]
    """
    seed = (seed or "").strip()
    if not seed:
        return None, "Amorce vide."
    loc, lang = location_language(env, geo, language)
    ckey = ("kfk", loc, lang, seed.lower(), int(limit))
    cached = _cache_get(ckey)
    if cached is not None:
        return cached, "OK (cache)."
    tasks = [{"keywords": [seed], "location_name": loc, "language_name": lang}]
    results, msg = _post(env, EP_KEYWORDS_FOR_KEYWORDS, tasks)
    if results is None:
        return None, msg
    out = []
    for res in results:
        kw = res.get("keyword")
        if not kw:
            continue
        sv = res.get("search_volume")
        out.append(
            {
                "keyword": kw,
                "volume": int(sv) if isinstance(sv, (int, float)) else None,
                "cpc": float(res["cpc"]) if isinstance(res.get("cpc"), (int, float)) else None,
                "competition": _norm_competition(res.get("competition")),
            }
        )
        if len(out) >= int(limit):
            break
    _cache_set(ckey, out)
    return out, "OK"
