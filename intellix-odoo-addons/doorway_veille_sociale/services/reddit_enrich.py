# -*- coding: utf-8 -*-
"""Enrichit un signal Discussions Google Alerts avec un permalink Reddit.

Réutilise query_collect.reddit_search + l'OAuth RedditService déjà en place.
Ne jamais inventer de lien : vide si le match n'est pas fiable.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from odoo.addons.doorway_veille_sociale.services.query_collect import reddit_search
from odoo.addons.doorway_veille_sociale.services.reddit_service import RedditService
from odoo.addons.doorway_veille_sociale.services.url_helpers import (
    is_subreddit_home,
    subreddit_name,
    title_search_tokens,
    unwrap_google_url_redirect,
)

_logger = logging.getLogger(__name__)

# Fenêtre autour de pubDate (secondes) — 3 jours.
TIME_WINDOW_S = 3 * 24 * 3600
MIN_TOKEN_HITS = 2


def _created_utc(post: dict) -> float:
    try:
        return float(post.get("created_utc") or 0)
    except (TypeError, ValueError):
        return 0.0


def _signal_ts(signal) -> float:
    raw = getattr(signal, "date_post", None) or getattr(signal, "date_detection", None)
    if not raw:
        return 0.0
    if hasattr(raw, "timestamp"):
        dt = raw
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    try:
        txt = str(raw).replace("Z", "").replace("T", " ")[:19]
        return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _score_post(post: dict, tokens: list[str], signal_ts: float) -> int:
    title = (post.get("title") or "").lower()
    hits = sum(1 for tok in tokens if tok.lower() in title)
    if hits < 1:
        return 0
    created = _created_utc(post)
    if signal_ts and created:
        delta = abs(created - signal_ts)
        if delta > TIME_WINDOW_S:
            return 0
        # plus proche = mieux
        closeness = max(0, int(10 - delta / 3600))
    else:
        closeness = 1
    return hits * 10 + closeness


def _permalink(post: dict) -> str:
    perm = (post.get("permalink") or "").strip()
    if not perm:
        return ""
    if perm.startswith("http"):
        return perm
    return "https://www.reddit.com%s" % perm


def _oauth_headers(env):
    cfg = env["doorway.veille.config"].sudo().get_config()
    svc = RedditService(env)
    if not svc.credentials_ok(cfg):
        return None, False
    token = svc._access_token(cfg)
    if not token.get("ok"):
        return None, False
    return svc._auth_headers(cfg, token["token"]), True


def find_reddit_permalink(env, signal) -> str:
    """Retourne un permalink ou '' — jamais une home inventée."""
    if (getattr(signal, "source", "") or "") != "google_alerts":
        return ""
    raw = unwrap_google_url_redirect(signal.url or "")
    resolved = (getattr(signal, "url_resolue", None) or raw or "").strip()
    if not is_subreddit_home(resolved) and not is_subreddit_home(raw):
        return ""
    sub = subreddit_name(resolved or raw)
    if not sub:
        return ""
    tokens = title_search_tokens(signal.titre or signal.resume or "")
    if not tokens:
        return ""
    query = " ".join(tokens[:5])
    headers, oauth = _oauth_headers(env)
    try:
        posts = reddit_search(sub, query, limit=12, headers=headers, oauth=oauth)
    except Exception as err:  # noqa: BLE001
        _logger.info("reddit enrich search failed r/%s: %s", sub, err)
        return ""
    signal_ts = _signal_ts(signal)
    ranked = []
    for post in posts:
        score = _score_post(post, tokens, signal_ts)
        if score >= MIN_TOKEN_HITS * 10:
            ranked.append((score, post))
    if not ranked:
        return ""
    ranked.sort(key=lambda x: x[0], reverse=True)
    best_score, best = ranked[0]
    # Exige un écart raisonnable si plusieurs candidats proches.
    if len(ranked) > 1 and ranked[1][0] == best_score:
        # deux scores identiques → trop ambigu
        return ""
    link = _permalink(best)
    if not link or is_subreddit_home(link):
        return ""
    return link


def enrich_signal(signal) -> str:
    """Écrit url_enrichie si un match fiable existe. N'écrase pas url_resolue."""
    if getattr(signal, "url_enrichie", None):
        return signal.url_enrichie
    link = find_reddit_permalink(signal.env, signal)
    if link:
        signal.sudo().write({"url_enrichie": link})
    return link or ""
