# -*- coding: utf-8 -*-
"""Résolution des URLs veille (Google News RSS, Reddit, etc.)."""
import base64
import logging
import re
from urllib.parse import quote_plus, urlparse

import requests

from odoo.addons.doorway_veille_sociale.services.url_helpers import (
    is_google_news_article,
    unwrap_google_url_redirect,
)

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)

# Éditeurs fréquents dans les titres Google Alerts (suffixe « - Publisher »).
PUBLISHER_SITES = {
    "TVA Nouvelles": "https://www.tvanouvelles.ca",
    "Radio-Canada": "https://ici.radio-canada.ca",
    "Journal de Québec": "https://www.journaldequebec.com",
    "Journal de Montreal": "https://www.journaldemontreal.com",
    "Journal de Montréal": "https://www.journaldemontreal.com",
    "La Presse": "https://www.lapresse.ca",
    "Le Soleil": "https://www.lesoleil.com",
    "Le Droit": "https://www.ledroit.com",
    "Le Journal de Montréal": "https://www.journaldemontreal.com",
    "Le Journal de Québec": "https://www.journaldequebec.com",
    "Les Affaires": "https://www.lesaffaires.com",
    "La Tribune": "https://www.latribune.ca",
    "CBC": "https://www.cbc.ca",
    "RCI": "https://ici.radio-canada.ca",
}


class VeilleUrlResolver:
    def __init__(self, env):
        self.env = env

    def resolve(self, signal):
        """Retourne la meilleure URL à ouvrir dans le navigateur."""
        url = (signal.url or "").strip()
        if signal.url_resolue:
            return signal.url_resolue

        if signal.source == "google_alerts" or self._is_google_news_url(url):
            resolved = self._resolve_google_alerts(signal, url)
            if resolved:
                return resolved

        if signal.source == "reddit" or "reddit.com" in url:
            resolved = self._resolve_reddit(url)
            if resolved:
                return resolved

        if url and not self._is_internal_odoo_url(url):
            return url

        editeur = (signal.url_editeur or "").strip()
        if editeur:
            return editeur

        title = (signal.titre or signal.resume or "").strip()
        if title:
            return self._google_search(title)

        return url or False

    @staticmethod
    def _is_google_news_url(url):
        return bool(url and "news.google.com" in url and "/articles/" in url)

    @staticmethod
    def _is_internal_odoo_url(url):
        return bool(
            url
            and (
                "/doorway/veille/webhook" in url
                or url.rstrip("/").endswith("intellixcrm.com")
            )
        )

    @staticmethod
    def extract_publisher_from_title(title):
        """Extrait le site éditeur depuis « Titre - Publisher »."""
        if not title or " - " not in title:
            return False, False
        parts = title.rsplit(" - ", 1)
        publisher = parts[1].strip()
        site = PUBLISHER_SITES.get(publisher)
        return site, publisher

    @classmethod
    def extract_publisher_url(cls, title):
        site, _publisher = cls.extract_publisher_from_title(title)
        return site

    def _resolve_google_alerts(self, signal, url):
        title = (signal.titre or signal.resume or "").strip()
        editeur = (signal.url_editeur or "").strip()
        if not editeur:
            editeur = self.extract_publisher_url(title) or ""

        unwrapped = unwrap_google_url_redirect(url)
        if unwrapped and unwrapped != url and not is_google_news_article(unwrapped):
            return unwrapped

        decoded = self.legacy_decode_google_news(url) or self._try_decode_google_news(url)
        if decoded and decoded.startswith("http"):
            return decoded

        if editeur and title:
            domain = urlparse(editeur).netloc.replace("www.", "")
            short_title = title.split(" - ")[0].strip() if " - " in title else title
            if domain and short_title:
                return (
                    "https://www.google.com/search?q=site:%s+%s"
                    % (domain, quote_plus(short_title))
                )

        if title:
            return self._google_search(title)

        return editeur or url

    def _resolve_reddit(self, url):
        if not url:
            return False
        url = url.split("?")[0].rstrip("/")
        if "reddit.com" not in url:
            return url
        # Normalise vers www.reddit.com (lisible dans le navigateur).
        url = re.sub(r"https?://(old\.|np\.|m\.)?reddit\.com", "https://www.reddit.com", url)
        post_id = self._reddit_post_id(url)
        if post_id:
            return "https://www.reddit.com/comments/%s/" % post_id
        return url

    @staticmethod
    def _reddit_post_id(url):
        match = re.search(r"/comments/([a-z0-9]+)/", url or "", re.I)
        return match.group(1) if match else False

    @staticmethod
    def _google_search(query):
        return "https://www.google.com/search?q=%s" % quote_plus(query)

    def _try_decode_google_news(self, url):
        """Tente le décodage batchexecute Google (articles récents)."""
        if not self._is_google_news_url(url):
            return False
        try:
            article_path = url.split("news.google.com")[-1].split("?")[0]
            fetch_url = "https://news.google.com%s?hl=fr-CA&gl=CA&ceid=CA:fr" % article_path
            page = requests.get(
                fetch_url,
                headers={"User-Agent": BROWSER_UA, "Accept-Language": "fr-CA,fr;q=0.9"},
                timeout=REQUEST_TIMEOUT,
            )
            if page.status_code >= 400:
                return False
            match = re.search(r'data-p="([^"]+)"', page.text)
            if not match:
                return False
            import json

            raw = match.group(1).replace("&quot;", '"')
            data = json.loads(raw.replace("%.@.", '["garturlreq",'))
            payload = {
                "f.req": json.dumps(
                    [[["Fbv4je", json.dumps(data[:-6] + data[-2:]), "null", "generic"]]]
                )
            }
            resp = requests.post(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "User-Agent": BROWSER_UA,
                },
                timeout=REQUEST_TIMEOUT,
            )
            text = resp.text
            if text.startswith(")]}'"):
                text = text[5:]
            outer = json.loads(text)
            inner = json.loads(outer[0][2])
            decoded = inner[1]
            if decoded and str(decoded).startswith("http"):
                return decoded
        except Exception as error:  # noqa: BLE001
            _logger.debug("Decode Google News échoué: %s", error)
        return False

    @classmethod
    def legacy_decode_google_news(cls, url):
        """Ancien format Base64 (articles Google News legacy)."""
        try:
            path = urlparse(url).path.split("/")
            if len(path) < 2 or path[-2] != "articles":
                return False
            b64 = path[-1].split("?")[0]
            pad = "=" * (-len(b64) % 4)
            raw = base64.urlsafe_b64decode(b64 + pad)
            s = raw.decode("latin-1", errors="ignore")
            prefix = bytes([0x08, 0x13, 0x22]).decode("latin-1")
            suffix = bytes([0xD2, 0x01, 0x00]).decode("latin-1")
            if s.startswith(prefix):
                s = s[len(prefix) :]
            if s.endswith(suffix):
                s = s[: -len(suffix)]
            ln = ord(s[0])
            if ln >= 0x80:
                s = s[2 : ln + 2]
            else:
                s = s[1 : ln + 1]
            if s.startswith("http"):
                return s
        except Exception:  # noqa: BLE001
            pass
        return False
