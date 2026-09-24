# -*- coding: utf-8 -*-
import logging
import re
import urllib.parse

import requests

from ..base_scraper import BaseScraper

_logger = logging.getLogger(__name__)

_BAD_WEBSITE = (
    "moncallcenter", "marocannuaire", "telecontact", "kerix",
    "facebook", "linkedin", "twitter", "instagram", "youtube", "annuaire",
    "avito", "jiji", "marocannonces",
)


class AvitoMaScraper(BaseScraper):
    source_key = "avito_ma"

    def scrape(self):
        leads = []
        kw = self.mot_cle.lower().replace(" ", "-").replace("'", "-")
        ville = self.region.lower().replace(" ", "-")
        urls = [
            f"https://www.avito.ma/fr/{ville}/{kw}--Services",
            f"https://www.avito.ma/fr/maroc/{kw}--Services?r={ville}",
        ]
        for base_url in urls[:1]:
            for page in range(1, self.max_pages + 1):
                url = base_url if page == 1 else f"{base_url}?o={page}"
                html = self._safe_get(url)
                soup = self._soup(html)
                if not soup:
                    break
                cards = soup.find_all(
                    ["article", "div"],
                    attrs={"data-testid": re.compile(r"listing|adcard|result", re.I)},
                )
                if not cards:
                    cards = soup.find_all(
                        ["article", "li"],
                        class_=re.compile(r"sc-|listing|result|adCard", re.I),
                    )
                if not cards:
                    break
                count = 0
                for card in cards:
                    body = card.get_text(" ", strip=True)
                    name_tag = card.find(
                        ["h2", "h3", "strong", "span"],
                        class_=re.compile(r"title|name|header|seller", re.I),
                    )
                    name = name_tag.get_text(strip=True) if name_tag else ""
                    if not name:
                        lines = [l.strip() for l in body.split("\n") if len(l.strip()) > 5]
                        name = lines[0][:80] if lines else ""
                    if not name or len(name) < 3:
                        continue
                    a_tag = card.find("a", href=re.compile(r"/fr/"))
                    detail = ""
                    if a_tag:
                        href = a_tag.get("href", "")
                        detail = "https://www.avito.ma" + href if href.startswith("/") else href
                    phone = self._find_morocco_phone(body)
                    email = self._find_email(body)
                    if not phone and detail:
                        rd = self._safe_get(detail)
                        if rd:
                            phone = self._find_morocco_phone(rd)
                            if not email:
                                email = self._find_email(rd)
                    lead = self._lead(
                        name, phone=phone, email=email, city=self.region,
                        source_key=self.source_key, source_url=detail or url,
                    )
                    if lead:
                        leads.append(lead)
                        count += 1
                if count == 0:
                    break
        return leads


class MarocAnnuaireScraper(BaseScraper):
    source_key = "marocannuaire_org"

    def scrape(self):
        leads = []
        kw_enc = requests.utils.quote(self.mot_cle)
        ville = self.region.upper()
        for page in range(0, self.max_pages):
            url = (
                "https://www.marocannuaire.org/Annuaire/Liste_activite.php"
                f"?activite={kw_enc}&ville={ville}&p={page}"
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            links = soup.find_all("a", href=re.compile(r"Details_infos\.php\?id=\d+"))
            if not links:
                break
            for a in links:
                name = " ".join(a.get_text().split())
                if not name or len(name) < 3:
                    continue
                href = a.get("href", "")
                full = (
                    "https://www.marocannuaire.org/Annuaire/" + href
                    if not href.startswith("http")
                    else href
                )
                rd = self._safe_get(full)
                body = self._soup(rd).get_text(" ") if rd else ""
                dsoup = self._soup(rd) if rd else None
                lead = self._lead(
                    name,
                    phone=self._find_morocco_phone(body),
                    email=self._find_email(body),
                    website=self._find_website_filtered(dsoup) if dsoup else "",
                    address=self.region,
                    city=self.region,
                    source_key=self.source_key,
                    source_url=full,
                )
                if lead:
                    leads.append(lead)
        return leads


class MarocAnnoncesScraper(BaseScraper):
    source_key = "marocannonces_com"

    def scrape(self):
        leads = []
        kw = requests.utils.quote(self.mot_cle)
        ville = self.region.lower().replace(" ", "-")
        urls = [
            f"https://www.marocannonces.com/maroc/services-b2b?q={kw}&region={ville}",
            f"https://www.marocannonces.com/maroc/?q={kw}&region={ville}",
        ]
        for base_url in urls[:1]:
            for page in range(1, self.max_pages + 1):
                url = base_url if page == 1 else f"{base_url}&page={page}"
                html = self._safe_get(url)
                soup = self._soup(html)
                if not soup:
                    break
                cards = soup.find_all(
                    ["div", "li", "article"],
                    class_=re.compile(r"annonce|listing|result|item|card", re.I),
                )
                if not cards:
                    break
                count = 0
                for card in cards:
                    name_tag = card.find(["h2", "h3", "h4", "strong", "a"])
                    name = name_tag.get_text(strip=True)[:80] if name_tag else ""
                    if not name or len(name) < 3:
                        continue
                    body = card.get_text(" ", strip=True)
                    a_tag = card.find("a", href=True)
                    detail = ""
                    if a_tag:
                        href = a_tag["href"]
                        detail = (
                            "https://www.marocannonces.com" + href
                            if href.startswith("/")
                            else href
                        )
                    phone = self._find_morocco_phone(body)
                    email = self._find_email(body)
                    if not phone and detail:
                        rd = self._safe_get(detail)
                        if rd:
                            phone = self._find_morocco_phone(rd)
                            if not email:
                                email = self._find_email(rd)
                    lead = self._lead(
                        name, phone=phone, email=email, city=self.region,
                        source_key=self.source_key, source_url=detail or url,
                    )
                    if lead:
                        leads.append(lead)
                        count += 1
                if count == 0:
                    break
        return leads


class TelecontactMaScraper(BaseScraper):
    source_key = "telecontact_ma"

    def scrape(self):
        leads = []
        kw_slug = self.mot_cle.lower().replace(" ", "-").replace("'", "-")
        ville = self.region.lower()
        for page in range(1, self.max_pages + 1):
            url = (
                f"https://www.telecontact.ma/liens/{kw_slug}/{ville}"
                f"{'' if page == 1 else f'/{page}/'}.php"
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            cards = soup.find_all(
                ["div", "li"],
                class_=re.compile(r"result|item|fiche|listing|card", re.I),
            )
            if not cards:
                break
            for card in cards:
                name_tag = card.find(["h2", "h3", "h4", "strong"])
                name = " ".join(name_tag.get_text().split()) if name_tag else ""
                if not name or len(name) < 3:
                    continue
                body = card.get_text(" ")
                lead = self._lead(
                    name,
                    phone=self._find_morocco_phone(body),
                    email=self._find_email(body),
                    website=self._find_website_filtered(card),
                    city=self.region,
                    source_key=self.source_key,
                    source_url=url,
                )
                if lead:
                    leads.append(lead)
        return leads


class KerixMaScraper(BaseScraper):
    source_key = "kerix_ma"

    def scrape(self):
        leads = []
        slug = self.mot_cle.lower().replace(" ", "-")
        for page in range(1, self.max_pages + 1):
            url = f"https://www.kerix.net/fr/annuaire-entreprise/{slug}-R{page}.html"
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            cards = soup.find_all(
                ["div", "article"],
                class_=re.compile(r"company|entreprise|result|card|listing", re.I),
            )
            if not cards:
                break
            for card in cards:
                name_tag = card.find(["h2", "h3", "h4", "a", "strong"])
                name = " ".join(name_tag.get_text().split()) if name_tag else ""
                if not name or len(name) < 3:
                    continue
                body = card.get_text(" ")
                if self.region.lower() not in body.lower():
                    continue
                lead = self._lead(
                    name,
                    phone=self._find_morocco_phone(body),
                    email=self._find_email(body),
                    website=self._find_website_filtered(card),
                    city=self.region,
                    source_key=self.source_key,
                    source_url=url,
                )
                if lead:
                    leads.append(lead)
        return leads


class MoncallcenterMaScraper(BaseScraper):
    source_key = "moncallcenter_ma"

    def scrape(self):
        leads = []
        base = "https://www.moncallcenter.ma"
        html = self._safe_get(f"{base}/centres-appels.php?ville={self.region}")
        soup = self._soup(html)
        if not soup:
            return leads
        slugs = set()
        for a in soup.find_all("a", href=True):
            h = a["href"].strip("/")
            if h and "/" not in h and len(h) > 2:
                slugs.add(h)
        for slug in list(slugs)[: min(60, self.max_pages * 10)]:
            rd = self._safe_get(f"{base}/{slug}")
            dsoup = self._soup(rd)
            if not dsoup:
                continue
            h1 = dsoup.find("h1")
            name = " ".join(h1.get_text().split()) if h1 else ""
            if not name:
                continue
            body = dsoup.get_text(" ")
            lead = self._lead(
                name,
                phone=self._find_morocco_phone(body),
                email=self._find_email(body),
                website=self._find_website_filtered(dsoup),
                city=self.region,
                source_key=self.source_key,
                source_url=f"{base}/{slug}",
            )
            if lead:
                leads.append(lead)
        return leads


class JijiMaScraper(BaseScraper):
    source_key = "jiji_ma"

    def scrape(self):
        leads = []
        kw = requests.utils.quote(self.mot_cle)
        ville = self.region.lower()
        urls = [
            f"https://jiji.ma/maroc/services?query={kw}&region={ville}",
            f"https://jiji.ma/maroc?query={kw}&region={ville}",
        ]
        for base_url in urls[:1]:
            for page in range(1, self.max_pages + 1):
                url = base_url if page == 1 else f"{base_url}&page={page}"
                html = self._safe_get(url)
                soup = self._soup(html)
                if not soup:
                    break
                cards = soup.find_all(
                    ["article", "div", "li"],
                    class_=re.compile(r"b-list|listing|item|card|advert", re.I),
                )
                if not cards:
                    break
                count = 0
                for card in cards:
                    name_tag = card.find(
                        ["h3", "h2", "span"],
                        class_=re.compile(r"title|name|header", re.I),
                    )
                    name = name_tag.get_text(strip=True)[:80] if name_tag else ""
                    if not name or len(name) < 3:
                        continue
                    body = card.get_text(" ", strip=True)
                    phone = self._find_morocco_phone(body)
                    a_tag = card.find("a", href=True)
                    detail = ""
                    if a_tag:
                        href = a_tag["href"]
                        detail = "https://jiji.ma" + href if href.startswith("/") else href
                    if not phone and detail:
                        rd = self._safe_get(detail)
                        if rd:
                            phone = self._find_morocco_phone(rd)
                    lead = self._lead(
                        name, phone=phone, email=self._find_email(body),
                        city=self.region, source_key=self.source_key,
                        source_url=detail or url,
                    )
                    if lead:
                        leads.append(lead)
                        count += 1
                if count == 0:
                    break
        return leads


class ExpressBazarMaScraper(BaseScraper):
    source_key = "expressbazar_ma"

    def scrape(self):
        leads = []
        kw = requests.utils.quote(self.mot_cle)
        ville = self.region.lower()
        for page in range(1, self.max_pages + 1):
            url = (
                f"https://www.expressbazar.ma/recherche?q={kw}&ville={ville}&page={page}"
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            cards = soup.find_all(
                ["div", "article"],
                class_=re.compile(r"annonce|listing|item|card|result", re.I),
            )
            if not cards:
                break
            for card in cards:
                name_tag = card.find(["h2", "h3", "h4", "strong"])
                name = name_tag.get_text(strip=True)[:80] if name_tag else ""
                if not name or len(name) < 3:
                    continue
                body = card.get_text(" ", strip=True)
                lead = self._lead(
                    name,
                    phone=self._find_morocco_phone(body),
                    email=self._find_email(body),
                    website=self._find_website_filtered(card),
                    city=self.region,
                    source_key=self.source_key,
                    source_url=url,
                )
                if lead:
                    leads.append(lead)
        return leads


class KhidmatMaScraper(BaseScraper):
    source_key = "khidmat_ma"

    def scrape(self):
        leads = []
        kw = requests.utils.quote(self.mot_cle)
        ville = self.region.lower()
        for page in range(1, self.max_pages + 1):
            url = f"https://www.khidmat.ma/services?q={kw}&ville={ville}&page={page}"
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            cards = soup.find_all(
                ["div", "article", "li"],
                class_=re.compile(r"prestataire|service|listing|card|item", re.I),
            )
            if not cards:
                break
            for card in cards:
                name_tag = card.find(
                    ["h2", "h3", "strong", "span"],
                    class_=re.compile(r"name|title|prestataire", re.I),
                )
                name = name_tag.get_text(strip=True)[:80] if name_tag else ""
                if not name or len(name) < 3:
                    continue
                body = card.get_text(" ", strip=True)
                lead = self._lead(
                    name,
                    phone=self._find_morocco_phone(body),
                    email=self._find_email(body),
                    website=self._find_website_filtered(card),
                    city=self.region,
                    source_key=self.source_key,
                    source_url=url,
                )
                if lead:
                    leads.append(lead)
        return leads


# Helpers Morocco
def _morocco_phone_mixin(cls):
    def _find_morocco_phone(self, text):
        if not text:
            return ""
        m = re.search(
            r"(\+212[\s\.\-]?\d[\s\.\-]?\d{2}[\s\.\-]?\d{2}[\s\.\-]?\d{2}[\s\.\-]?\d{2}"
            r"|0[56]\d{8}|05[\s\.\-]?\d{2}[\s\.\-]?\d{2}[\s\.\-]?\d{2}[\s\.\-]?\d{2})",
            str(text),
        )
        if not m:
            return self._find_phone(text)
        d = re.sub(r"[^\d+]", "", m.group(0))
        if d.startswith("00212"):
            d = "+" + d[2:]
        if len(d) == 10 and d.startswith("0"):
            d = "+212" + d[1:]
        return d

    def _find_website_filtered(self, soup):
        if not soup:
            return ""
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and not any(d in h for d in _BAD_WEBSITE):
                return h.split("?")[0].rstrip("/")
        return ""

    cls._find_morocco_phone = _find_morocco_phone
    cls._find_website_filtered = _find_website_filtered
    return cls


for _scraper_cls in (
    AvitoMaScraper, MarocAnnuaireScraper, MarocAnnoncesScraper,
    TelecontactMaScraper, KerixMaScraper, MoncallcenterMaScraper,
    JijiMaScraper, ExpressBazarMaScraper, KhidmatMaScraper,
):
    _morocco_phone_mixin(_scraper_cls)
