# -*- coding: utf-8 -*-
"""Exclusion des sites de presse — à la collecte, toutes requêtes."""
import json
import os
import re
import unicodedata
from urllib.parse import urlparse

CONFIG_CANDIDATES = (
    os.environ.get("VEILLE_CONFIG_PATH") or "",
    "/odoo/custom/reseaux-sociaux/01_veille_config.json",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "module-reseaux-sociaux",
        "01_veille_config.json",
    ),
)

_CACHED = None


def _fold(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def load_config(path=None):
    global _CACHED
    if path:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    if _CACHED is not None:
        return _CACHED
    for candidate in CONFIG_CANDIDATES:
        if candidate and os.path.isfile(candidate):
            with open(candidate, encoding="utf-8") as handle:
                _CACHED = json.load(handle)
                return _CACHED
    _CACHED = {"media_exclude": {"domains": [], "publisher_suffixes": []}, "sources": {}}
    return _CACHED


def host_of(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://%s" % raw
    try:
        return (urlparse(raw).hostname or "").replace("www.", "").lower()
    except ValueError:
        return ""


def _domain_matches(host, domain):
    if not host or not domain:
        return False
    return host == domain or host.endswith("." + domain)


def _publisher_from_title(title):
    text = str(title or "")
    if " - " not in text:
        return ""
    return text.rsplit(" - ", 1)[-1].strip()


def is_media_source(row, config=None):
    cfg = config or load_config()
    media = cfg.get("media_exclude") or {}
    domains = media.get("domains") or []
    suffixes = media.get("publisher_suffixes") or []
    urls = [
        row.get("url_editeur") if isinstance(row, dict) else getattr(row, "url_editeur", ""),
        row.get("url") if isinstance(row, dict) else getattr(row, "url", ""),
        row.get("url_resolue") if isinstance(row, dict) else getattr(row, "url_resolue", ""),
        row.get("link") if isinstance(row, dict) else "",
    ]
    title = row.get("titre") if isinstance(row, dict) else getattr(row, "titre", "")
    title = title or (row.get("title") if isinstance(row, dict) else "")
    for url in urls:
        host = host_of(url)
        if not host:
            continue
        if host == "news.google.com":
            pub = _publisher_from_title(title)
            folded_pub = _fold(pub)
            if pub and any(_fold(s) in folded_pub or folded_pub == _fold(s) for s in suffixes):
                return True
            if pub and any(_fold(d.split(".")[0]) in folded_pub for d in domains):
                return True
            continue
        if any(_domain_matches(host, d) for d in domains):
            return True
    folded_title = _fold(title)
    for suffix in suffixes:
        if folded_title.endswith(" - " + _fold(suffix)) or (" - %s" % suffix) in str(title):
            return True
    return False


def tag_branche_from_queries(row, config=None):
    tagged = _fold(
        (row.get("query_branche") if isinstance(row, dict) else "")
        or (row.get("branche_source") if isinstance(row, dict) else "")
    )
    if tagged:
        return tagged
    cfg = config or load_config()
    blob = _fold(
        " ".join(
            filter(
                None,
                [
                    row.get("query_id") if isinstance(row, dict) else "",
                    row.get("signal_id_externe")
                    if isinstance(row, dict)
                    else getattr(row, "signal_id_externe", ""),
                ],
            )
        )
    )
    queries = []
    queries.extend(((cfg.get("sources") or {}).get("reddit") or {}).get("queries") or [])
    queries.extend(((cfg.get("sources") or {}).get("google_alerts") or {}).get("queries") or [])
    for query in queries:
        qid = _fold(query.get("id") or "")
        if qid and qid in blob:
            return query.get("branche") or ""
    return ""
