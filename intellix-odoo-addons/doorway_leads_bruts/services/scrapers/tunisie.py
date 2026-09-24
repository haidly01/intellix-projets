# -*- coding: utf-8 -*-
"""Scrapers Tunisie — call centers / BPO."""
import logging
import re
import urllib.parse

from ..base_scraper import BaseScraper

_logger = logging.getLogger(__name__)


def _find_tunisia_phone(text):
    if not text:
        return ""
    patterns = [
        r"(?:\+216|00216|216)[\s\-]?([2-9]\d{7})",
        r"(?<!\d)([2-9]\d{7})(?!\d)",
    ]
    for pat in patterns:
        m = re.search(pat, text.replace("\u00a0", " "))
        if m:
            digits = m.group(1) if m.lastindex else m.group(0)
            digits = re.sub(r"\D", "", digits)
            if len(digits) == 8:
                return digits
    return ""


class TunisieAnnonceScraper(BaseScraper):
    """tunisie-annonce.com — recrutement / services."""

    source_key = "tunisie_annonce_tn"

    def scrape(self):
        leads = []
        kw = urllib.parse.quote(self.mot_cle)
        for page in range(1, self.max_pages + 1):
            url = (
                "https://www.tunisie-annonce.com/AnnoncesRecherche.php"
                "?recherche=%s&page=%s" % (kw, page)
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            items = soup.find_all(["div", "article", "tr"], class_=re.compile(r"annonce|result|listing", re.I))
            if not items:
                items = soup.find_all("a", href=re.compile(r"AnnonceImmobilier|Details", re.I))
            count = 0
            for item in items[:40]:
                body = item.get_text(" ", strip=True)
                if len(body) < 20:
                    continue
                if "call" not in body.lower() and "appel" not in body.lower() and "téléconseil" not in body.lower():
                    if "centre" not in body.lower() and "bpo" not in body.lower():
                        continue
                name = body[:80].split("  ")[0]
                phone = _find_tunisia_phone(body)
                phone_fmt = ("+216%s" % phone) if phone else ""
                lead = self._lead(
                    name, phone=phone_fmt, city=self.region,
                    source_key=self.source_key, source_url=url,
                )
                if lead:
                    leads.append(lead)
                    count += 1
            if count == 0:
                break
        return leads


class KeejobTnScraper(BaseScraper):
    """keejob.com — offres call center."""

    source_key = "keejob_tn"

    def scrape(self):
        leads = []
        kw = urllib.parse.quote(self.mot_cle)
        url = "https://www.keejob.com/offres-emploi/?keywords=%s" % kw
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.find_all(["article", "div"], class_=re.compile(r"job|offer|card", re.I))[:50]:
            body = card.get_text(" ", strip=True)
            company_tag = card.find(["h2", "h3", "strong", "span"], class_=re.compile(r"company|employer", re.I))
            name = company_tag.get_text(strip=True) if company_tag else body[:60]
            if not name or len(name) < 3:
                continue
            phone = _find_tunisia_phone(body)
            a = card.find("a", href=True)
            detail = ("https://www.keejob.com" + a["href"]) if a and a["href"].startswith("/") else url
            phone_fmt = ("+216%s" % phone) if phone else ""
            lead = self._lead(
                name, phone=phone_fmt, city=self.region,
                source_key=self.source_key, source_url=detail,
            )
            if lead:
                leads.append(lead)
        return leads


class GoogleMapsTnScraper(BaseScraper):
    """Google Maps Tunisie via scraper commun."""

    source_key = "google_maps_tn"

    def scrape(self):
        from .common import GoogleMapsScraper

        api_key = ""
        if self.env:
            api_key = self.env["doorway.credit.config"].get_config().google_maps_api_key
        scraper = GoogleMapsScraper(
            self.mot_cle,
            self.region,
            rayon_km=self.rayon_km,
            max_pages=self.max_pages,
            api_key=api_key,
            pays="Tunisia",
        )
        return scraper.scrape()
