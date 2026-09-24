# -*- coding: utf-8 -*-
"""Collecte Reddit taguée (Coins Marocain / Coins Québec) — sources d'engagement."""
import logging

import requests

from odoo.addons.doorway_veille_sociale.services.media_exclude import (
    is_media_source,
    load_config,
)

_logger = logging.getLogger(__name__)
UA = "DoorwayVeille/1.5 (engagement collector; +https://agencedoorway.com)"


def reddit_search(sub, query, limit=10, headers=None, oauth=False):
    host = "https://oauth.reddit.com" if oauth else "https://www.reddit.com"
    url = "%s/r/%s/search" % (host, sub)
    if not oauth:
        url += ".json"
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    resp = requests.get(
        url,
        params={
            "q": query,
            "restrict_sr": "1",
            "sort": "new",
            "t": "year",
            "limit": str(limit or 10),
        },
        headers=hdrs,
        timeout=20,
    )
    resp.raise_for_status()
    children = ((resp.json() or {}).get("data") or {}).get("children") or []
    return [c.get("data") or {} for c in children]


def collect_tagged_payloads(config=None, headers=None, oauth=False):
    cfg = config or load_config()
    reddit = (cfg.get("sources") or {}).get("reddit") or {}
    out = []
    if reddit.get("enabled") is False:
        return out
    for query in reddit.get("queries") or []:
        for sub in query.get("subs") or []:
            try:
                posts = reddit_search(
                    sub,
                    query.get("q") or "",
                    query.get("limit"),
                    headers=headers,
                    oauth=oauth,
                )
            except Exception as err:  # noqa: BLE001
                _logger.warning("collect reddit %s/%s: %s", query.get("id"), sub, err)
                continue
            for post in posts:
                permalink = post.get("permalink") or ""
                url = ("https://www.reddit.com%s" % permalink) if permalink else (post.get("url") or "")
                payload = {
                    "signal_id_externe": "%s:%s"
                    % (query.get("id"), post.get("id") or post.get("name") or ""),
                    "source": "reddit",
                    "plateforme": query.get("branche"),
                    "query_id": query.get("id"),
                    "query_branche": query.get("branche"),
                    "auteur": ("u/%s" % post["author"]) if post.get("author") else False,
                    "titre": post.get("title") or "",
                    "texte": (post.get("selftext") or "")[:6000],
                    "url": url,
                    "url_editeur": url,
                    "statut": "en_attente",
                    "marche": "autre" if query.get("branche") == "coins_marocain" else "quebec",
                    "pre_score": 40,
                    "score_final": 40,
                    "score_intention": 4,
                    "temperature": "warm",
                    "resume": "Requête %s → %s" % (query.get("id"), query.get("branche")),
                }
                if is_media_source(payload, cfg):
                    continue
                out.append(payload)
    return out
