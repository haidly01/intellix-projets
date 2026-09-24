# -*- coding: utf-8 -*-
"""Analyse PURE d'un SERP normalisé (aucun I/O, aucune dépendance réseau).

Sert à :
  - trouver la meilleure position d'un domaine dans les résultats (rank tracking) ;
  - dériver un PROXY de difficulté à partir de la force des domaines classés ;
  - extraire des signaux exploitables (recherches associées, PAA, top domaines).

Toutes les fonctions sont défensives et ne lèvent jamais.
"""

# Domaines à forte autorité : leur présence en page 1 augmente la difficulté.
STRONG_DOMAINS = (
    "wikipedia.org", "amazon.", "youtube.com", "facebook.com", "linkedin.com",
    "instagram.com", "tripadvisor.", "yelp.", "reddit.com", "pinterest.",
    "gouv.", ".gov", "google.com", "apple.com", "microsoft.com", "booking.com",
    "homedepot.", "rona.", "canadiantire.", "leroymerlin.", "houzz.",
    "pagesjaunes.", "kijiji.", "indeed.", "glassdoor.",
)


def normalize_domain(url):
    """Renvoie le hôte sans scheme ni 'www.' (best-effort, jamais d'exception)."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        candidate = url if "://" in url else "http://" + url
        host = urlparse(candidate).netloc.lower()
        if not host:
            host = url.lower().split("/")[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return (url or "").lower()


def _matches(target_domain, result_domain):
    if not target_domain or not result_domain:
        return False
    target_domain = target_domain.lower()
    result_domain = result_domain.lower()
    return target_domain == result_domain or result_domain.endswith("." + target_domain) \
        or target_domain.endswith("." + result_domain) or target_domain in result_domain


def find_rank(serp, target_domain):
    """Renvoie la meilleure position du domaine dans le SERP.

    :returns: dict {found:bool, position:int (0 si absent), url:str, features:list}
    """
    result = {"found": False, "position": 0, "url": "", "features": []}
    if not isinstance(serp, dict):
        return result
    result["features"] = serp.get("features") or []
    target = normalize_domain(target_domain)
    if not target:
        return result
    best_pos = None
    best_url = ""
    for item in serp.get("organic") or []:
        if not isinstance(item, dict):
            continue
        dom = item.get("domain") or normalize_domain(item.get("url"))
        if _matches(target, dom):
            try:
                pos = int(item.get("position") or 0)
            except (TypeError, ValueError):
                pos = 0
            if pos and (best_pos is None or pos < best_pos):
                best_pos = pos
                best_url = item.get("url") or ""
    if best_pos:
        result.update({"found": True, "position": best_pos, "url": best_url})
    return result


def _is_strong(domain):
    domain = (domain or "").lower()
    return any(token in domain for token in STRONG_DOMAINS)


def extract_signals(serp):
    """Dérive top domaines + un PROXY de difficulté (0-100) depuis le SERP.

    La difficulté est une ESTIMATION fondée sur la force/diversité des domaines
    classés en page 1 — jamais présentée comme un chiffre exact d'un outil tiers.
    """
    out = {
        "related": [],
        "paa": [],
        "top_domains": [],
        "difficulty": None,
        "difficulty_label": "N/A",
    }
    if not isinstance(serp, dict):
        return out
    out["related"] = (serp.get("related") or [])[:10]
    out["paa"] = (serp.get("paa") or [])[:10]

    organic = serp.get("organic") or []
    top = organic[:10]
    domains = []
    strong = 0
    for item in top:
        if not isinstance(item, dict):
            continue
        dom = item.get("domain") or normalize_domain(item.get("url"))
        if dom and dom not in domains:
            domains.append(dom)
        if _is_strong(dom):
            strong += 1
    out["top_domains"] = domains[:10]

    if top:
        # Proxy : part de domaines forts (0-70) + densité de gros acteurs (0-30).
        strong_ratio = strong / float(len(top))
        diversity_penalty = 1.0 - (len(set(domains)) / float(len(top)))  # peu de diversité = SERP verrouillé
        score = 30 + 55 * strong_ratio + 15 * diversity_penalty
        difficulty = int(max(1, min(100, round(score))))
        out["difficulty"] = difficulty
        out["difficulty_label"] = difficulty_band(difficulty)
    return out


def difficulty_band(difficulty):
    if difficulty is None:
        return "N/A"
    if difficulty < 35:
        return "Facile"
    if difficulty < 60:
        return "Moyen"
    if difficulty < 80:
        return "Difficile"
    return "Très difficile"
