# -*- coding: utf-8 -*-
"""Volume / métriques de mots-clés — sélection du fournisseur PLUGGABLE.

Fournisseur sélectionné par ``doorway_seo.keyword_volume_provider`` (défaut
``dataforseo``). Fournisseurs supportés :
  - ``dataforseo`` : volume + CPC + concurrence + difficulté RÉELS (cf.
    ``dataforseo_client``). Recommandé.
  - ``http`` : endpoint générique renvoyant {"volumes": {"<kw>": <int>}}.
  - sinon / non configuré / échec : volumes honnêtement « estimé » / « N/A »
    (jamais inventés).

Ne lève jamais : tout échec retombe sur « estimé ».

NOTE : le suivi de positionnement (SERP/rank) reste sur ``brightdata_client`` ;
ce module ne touche pas au rank tracking.
"""
import json
import logging

import requests

from . import config_loader, dataforseo_client, serp_analyzer

_logger = logging.getLogger(__name__)
TIMEOUT = 20


def is_available(env):
    return config_loader.keyword_volume_available(env)


def _estimated_entry():
    return {
        "volume": None,
        "label": "estimé",
        "source": "estimate",
        "cpc": None,
        "competition": "",
        "difficulty": None,
        "difficulty_label": "N/A",
    }


def lookup(env, keywords, geo="", language="fr"):
    """Renvoie {keyword: {volume, label, source, cpc, competition, difficulty,
    difficulty_label}}.

    Sans fournisseur réellement disponible (ou en cas d'échec) : entrées
    « estimé » (volume=None), jamais de chiffre inventé.
    """
    keywords = [k for k in (keywords or []) if isinstance(k, str) and k.strip()]
    result = {k: _estimated_entry() for k in keywords}
    if not keywords:
        return result

    cfg = config_loader.get_keyword_volume_config(env)
    if not cfg:
        return result
    provider = cfg.get("provider")

    if provider == "dataforseo":
        return _lookup_dataforseo(env, keywords, geo, language, result)
    if provider == "http" and cfg.get("endpoint"):
        return _lookup_http(env, cfg, keywords, geo, language, result)

    _logger.info("keyword_volume: provider '%s' non disponible → estimé", provider)
    return result


def _lookup_dataforseo(env, keywords, geo, language, result):
    if not config_loader.dataforseo_available(env):
        _logger.info("keyword_volume: DataForSEO non configuré → estimé")
        return result
    volumes, _vmsg = dataforseo_client.search_volume(env, keywords, geo=geo, language=language)
    kd, _kmsg = dataforseo_client.bulk_keyword_difficulty(env, keywords, geo=geo, language=language)
    volumes = volumes or {}
    kd = kd or {}
    for kw in keywords:
        entry = dict(result[kw])
        v = volumes.get(kw) or {}
        if v.get("volume") is not None:
            entry["volume"] = v["volume"]
            entry["label"] = "%d/mois" % v["volume"]
            entry["source"] = "dataforseo"
        if v.get("cpc") is not None:
            entry["cpc"] = v["cpc"]
        if v.get("competition"):
            entry["competition"] = v["competition"]
        if kw in kd:
            entry["difficulty"] = kd[kw]
            entry["difficulty_label"] = serp_analyzer.difficulty_band(kd[kw])
            if entry["source"] == "estimate":
                entry["source"] = "dataforseo"
        result[kw] = entry
    return result


def _lookup_http(env, cfg, keywords, geo, language, result):
    try:
        headers = {"Content-Type": "application/json"}
        if cfg.get("api_key"):
            headers["Authorization"] = "Bearer %s" % cfg["api_key"]
        resp = requests.post(
            cfg["endpoint"],
            headers=headers,
            data=json.dumps({"keywords": keywords, "geo": geo or "", "language": language or "fr"}),
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            volumes = (resp.json() or {}).get("volumes") or {}
            for kw in keywords:
                val = volumes.get(kw)
                if isinstance(val, (int, float)):
                    result[kw] = dict(
                        result[kw],
                        volume=int(val),
                        label="%d/mois" % int(val),
                        source="http",
                    )
        else:
            _logger.info("keyword_volume: HTTP %s → estimé", resp.status_code)
    except Exception as exc:  # noqa: BLE001
        _logger.info("keyword_volume: échec provider http (%s) → estimé", exc)
    return result
