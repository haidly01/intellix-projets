# -*- coding: utf-8 -*-
"""Classe de base pour tous les scrapers Leads Bruts."""
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

_logger = logging.getLogger(__name__)

PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}"
)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
QC_AREA_PHONE_RE = re.compile(
    r"(?:(?:\+?1[\s.-]?)?(?:\(?)(?:418|581|819|438|514|450)(?:\)?)[\s.-]?)\d{3}[\s.-]?\d{4}"
)


class BaseScraper:
    """Scraper HTTP partagé — hérité par chaque source."""

    USER_AGENT = (
        "Mozilla/5.0 (compatible; IntelliXLeadsBot/2.0; +https://intellixcrm.com)"
    )
    REQUEST_DELAY = 0.8

    use_brightdata = False

    def __init__(self, mot_cle, region, rayon_km=10, max_pages=5):
        self.mot_cle = (mot_cle or "").strip()
        self.region = (region or "").strip()
        self.rayon_km = rayon_km
        self.max_pages = max_pages
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def _safe_get(self, url, params=None, timeout=25):
        use_bd = getattr(self, "use_brightdata", False)
        if use_bd:
            try:
                from .brightdata_client import unlocker_get

                html = unlocker_get(url)
                if html:
                    time.sleep(self.REQUEST_DELAY)
                    return html
            except Exception as exc:
                _logger.warning("Bright Data fallback for %s: %s", url, exc)
        try:
            time.sleep(self.REQUEST_DELAY)
            resp = self.session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            _logger.warning("Scraper GET failed %s: %s", url, exc)
            if not use_bd:
                try:
                    from .brightdata_client import is_available, unlocker_get

                    if is_available():
                        html = unlocker_get(url)
                        if html:
                            return html
                except Exception:
                    pass
            return ""

    def _soup(self, html):
        if not html:
            return None
        return BeautifulSoup(html, "lxml")

    def _find_phone(self, text):
        if not text:
            return ""
        raw = str(text)
        toll_free = {"800", "888", "877", "866", "855", "844", "833"}
        for m in QC_AREA_PHONE_RE.finditer(raw):
            phone = m.group(0).strip()
            digits = re.sub(r"\D", "", phone)
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if len(digits) != 10:
                continue
            if digits[:3] in toll_free:
                continue
            return phone
        m = PHONE_RE.search(raw)
        if not m:
            return ""
        phone = m.group(0).strip()
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) == 10 and digits[:3] in ("418", "581", "819", "438", "514", "450"):
            if digits[:3] not in toll_free:
                return phone
        return ""

    def _find_email(self, text):
        if not text:
            return ""
        m = EMAIL_RE.search(str(text))
        return m.group(0).strip() if m else ""

    def _find_website(self, soup, base_url=""):
        if not soup:
            return ""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "facebook" not in href and "mailto:" not in href:
                return href
        return ""

    def _lead(self, name, phone="", email="", website="", address="", city="", source_key="", source_url=""):
        name = (name or "").strip()
        if not name:
            return None
        return {
            "name": name[:255],
            "phone": self._find_phone(phone) or self._find_phone(name),
            "email": self._find_email(email) or self._find_email(name),
            "website": (website or "").strip()[:255],
            "address": (address or "").strip()[:255],
            "city": (city or self.region or "").strip()[:128],
            "source_key": source_key,
            "source_url": (source_url or "").strip()[:512],
        }

    def scrape(self):
        """À surcharger — retourne list[dict]."""
        return []
