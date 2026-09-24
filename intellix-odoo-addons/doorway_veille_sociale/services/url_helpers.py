# -*- coding: utf-8 -*-
"""Helpers URL veille — unwrap Google Alerts + détection homes Reddit.

Fonctions pures (pas d'I/O) pour tests et ingestion.
Ne touche pas au décodage news.google.com/articles (url_resolver).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

GOOGLE_NEWS_ARTICLE_RE = re.compile(
    r"news\.google\.com/(?:rss/)?articles/",
    re.IGNORECASE,
)
# google.com/url?url=DESTINATION (Alerts Discussions / redirects).
GOOGLE_REDIRECT_HOSTS = ("google.com", "www.google.com", "news.google.com")
SUBREDDIT_HOME_RE = re.compile(
    r"^https?://(?:www\.|old\.|np\.|m\.)?reddit\.com/r/([^/]+)/?$",
    re.IGNORECASE,
)
SUBREDDIT_ANY_RE = re.compile(
    r"reddit\.com/r/([^/]+)",
    re.IGNORECASE,
)


def is_google_news_article(url: str | None) -> bool:
    return bool(url and GOOGLE_NEWS_ARTICLE_RE.search(url))


def unwrap_google_url_redirect(url: str | None) -> str:
    """Extrait url= d'un lien google.com/url?...&url=DESTINATION.

    Ne modifie pas news.google.com/articles/... (Partie 1).
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    if is_google_news_article(raw):
        return raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "google.com" or parsed.path.rstrip("/") != "/url":
        return raw
    qs = parse_qs(parsed.query)
    dest = (qs.get("url") or [""])[0]
    dest = unquote(dest or "").strip()
    if dest.startswith("http://") or dest.startswith("https://"):
        return dest
    return raw


def is_subreddit_home(url: str | None) -> bool:
    """True si l'URL est la home d'un subreddit, sans permalink /comments/."""
    raw = (url or "").split("?")[0].rstrip("/")
    if not raw or "/comments/" in raw:
        return False
    return bool(SUBREDDIT_HOME_RE.match(raw))


def subreddit_name(url: str | None) -> str:
    match = SUBREDDIT_ANY_RE.search(url or "")
    return (match.group(1) or "").strip() if match else ""


def title_search_tokens(title: str | None, limit: int = 8) -> list[str]:
    """Mots utiles pour une recherche Reddit (ignore le suffixe éditeur)."""
    text = (title or "").split(" - ")[0]
    words = re.findall(r"[A-Za-zÀ-ÿ0-9']{3,}", text)
    stop = {
        "the", "and", "for", "les", "des", "une", "pour", "avec", "dans",
        "sur", "plus", "que", "qui", "est", "are", "this", "that", "www",
        "http", "https", "reddit", "com",
    }
    out = []
    seen = set()
    for word in words:
        key = word.lower()
        if key in stop or key in seen:
            continue
        seen.add(key)
        out.append(word)
        if len(out) >= limit:
            break
    return out
