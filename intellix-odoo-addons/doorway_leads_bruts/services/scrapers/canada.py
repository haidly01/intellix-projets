# -*- coding: utf-8 -*-
import logging
import urllib.parse

from ..base_scraper import BaseScraper

_logger = logging.getLogger(__name__)


class YellowPagesCaScraper(BaseScraper):
    source_key = "yellowpages_ca"

    def scrape(self):
        leads = []
        for page in range(1, self.max_pages + 1):
            slug_kw = urllib.parse.quote(self.mot_cle.replace(" ", "+"))
            slug_loc = urllib.parse.quote(self.region.replace(" ", "+"))
            url = f"https://www.yellowpages.ca/search/si/{page}/{slug_kw}/{slug_loc}"
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            for card in soup.select(".listing--enhanced, .listing, .result"):
                info = card.select_one(".info, .listing__content") or card
                name_el = info.select_one("h3, .listing__name, a.business-name")
                phone_el = info.select_one(".phones, .listing__phone")
                if not name_el:
                    continue
                lead = self._lead(
                    name_el.get_text(strip=True),
                    phone=phone_el.get_text(strip=True) if phone_el else "",
                    city=self.region,
                    source_key=self.source_key,
                    source_url=url,
                )
                if lead:
                    leads.append(lead)
        return leads


class Canada411Scraper(BaseScraper):
    source_key = "canada411"

    def scrape(self):
        leads = []
        for page in range(1, self.max_pages + 1):
            url = (
                "https://www.canada411.ca/search/"
                f"?stype=si&pg={page}"
                f"&what={urllib.parse.quote(self.mot_cle)}"
                f"&where={urllib.parse.quote(self.region)}"
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            for item in soup.select(".c411Listing, .listing, .result-item"):
                name_el = item.select_one("h3, .name, a")
                phone_el = item.select_one(".phone, .listing-phone")
                if not name_el:
                    continue
                lead = self._lead(
                    name_el.get_text(strip=True),
                    phone=phone_el.get_text(strip=True) if phone_el else "",
                    city=self.region,
                    source_key=self.source_key,
                    source_url=url,
                )
                if lead:
                    leads.append(lead)
        return leads


class KijijiCaScraper(BaseScraper):
    source_key = "kijiji_ca"

    def scrape(self):
        leads = []
        url = (
            f"https://www.kijiji.ca/b-services/{urllib.parse.quote(self.region)}"
            f"/{urllib.parse.quote(self.mot_cle)}/k0c72"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for ad in soup.select("[data-testid='listing-card'], .search-item, article"):
            title = ad.select_one("h3, a.title, [data-testid='listing-title']")
            if not title:
                continue
            lead = self._lead(
                title.get_text(strip=True),
                phone=ad.get_text(),
                city=self.region,
                source_key=self.source_key,
                source_url=url,
            )
            if lead:
                leads.append(lead)
        return leads


class YelpCaScraper(BaseScraper):
    source_key = "yelp_ca"

    def scrape(self):
        leads = []
        url = (
            "https://www.yelp.ca/search"
            f"?find_desc={urllib.parse.quote(self.mot_cle)}"
            f"&find_loc={urllib.parse.quote(self.region)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select("[data-testid='serp-ia-card'], .businessName, li"):
            name_el = card.select_one("a, h3, h4")
            if not name_el:
                continue
            lead = self._lead(
                name_el.get_text(strip=True),
                phone=card.get_text(),
                city=self.region,
                source_key=self.source_key,
                source_url=url,
            )
            if lead:
                leads.append(lead)
        return leads

KIJIJI_IMMO_LOCATIONS = {
    "quebec": "ville-de-quebec",
    "ville-de-quebec": "ville-de-quebec",
    "quebec city": "ville-de-quebec",
    "montreal": "montreal",
    "laval": "laval",
    "levis": "levis",
}

LESPAC_REGION = {
    "quebec": ("quebec", "15398"),
    "ville-de-quebec": ("quebec", "15398"),
    "montreal": ("montreal", "17567"),
    "laval": ("laval", "17568"),
}


class KijijiImmoQcScraper(BaseScraper):
    """Kijiji immobilier - fiches detail via Bright Data Web Unlocker."""

    source_key = "kijiji_immo_ca"
    use_brightdata = True
    MAX_DETAILS = 30

    def _location_slug(self):
        key = (self.region or "quebec").lower().replace("é", "e").strip()
        return KIJIJI_IMMO_LOCATIONS.get(key, key.replace(" ", "-"))

    def _collect_detail_urls(self, soup):
        urls = []
        seen = set()
        for anchor in soup.select("a[href*='/v-']"):
            href = (anchor.get("href") or "").split("?")[0].strip()
            if not href or "/v-" not in href:
                continue
            if href.startswith("/"):
                href = "https://www.kijiji.ca" + href
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)
            if len(urls) >= self.MAX_DETAILS:
                break
        return urls

    def scrape(self):
        leads = []
        slug = self._location_slug()
        list_url = f"https://www.kijiji.ca/b-immobilier/{slug}/c34l1700280"
        html = self._safe_get(list_url)
        soup = self._soup(html)
        if not soup:
            return leads
        for detail_url in self._collect_detail_urls(soup):
            dhtml = self._safe_get(detail_url)
            if not dhtml:
                continue
            dsoup = self._soup(dhtml)
            title_el = dsoup.select_one("h1, [data-testid='ad-title']") if dsoup else None
            title = title_el.get_text(strip=True) if title_el else detail_url.rsplit("/", 1)[-1]
            phone = self._find_phone(dhtml)
            if not phone:
                continue
            lead = self._lead(
                title,
                phone=phone,
                city=self.region,
                source_key=self.source_key,
                source_url=detail_url,
            )
            if lead:
                leads.append(lead)
        return leads


class LespacImmoQcScraper(BaseScraper):
    """LesPAC immobilier residentiel - best-effort (mur login possible)."""

    source_key = "lespac_immo_ca"
    use_brightdata = True
    MAX_DETAILS = 20

    def _list_url(self):
        key = (self.region or "quebec").lower().replace("é", "e").strip()
        region_slug, region_id = LESPAC_REGION.get(key, ("quebec", "15398"))
        return (
            f"https://www.lespac.com/{region_slug}/"
            f"immobilier-achat-vente-residentiel_b37g{region_id}k1R2.jsa"
        )

    def _collect_detail_urls(self, soup):
        urls = []
        seen = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].split("#")[0].strip()
            if ".jsa" not in href or "_b37g" not in href:
                continue
            if "achat-vente-residentiel_b37" in href and href.endswith("k1R2.jsa"):
                continue
            if href.startswith("/"):
                href = "https://www.lespac.com" + href
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)
            if len(urls) >= self.MAX_DETAILS:
                break
        return urls

    def scrape(self):
        leads = []
        list_url = self._list_url()
        html = self._safe_get(list_url)
        soup = self._soup(html)
        if not soup:
            return leads
        for detail_url in self._collect_detail_urls(soup):
            dhtml = self._safe_get(detail_url)
            if not dhtml:
                continue
            dsoup = self._soup(dhtml)
            title_el = dsoup.select_one("h1, .title, [class*='title']") if dsoup else None
            title = title_el.get_text(strip=True) if title_el else detail_url.rsplit("/", 1)[-1]
            phone = self._find_phone(dhtml)
            if not phone:
                continue
            lead = self._lead(
                title,
                phone=phone,
                city=self.region,
                source_key=self.source_key,
                source_url=detail_url,
            )
            if lead:
                leads.append(lead)
        return leads


class CraigslistQcImmoScraper(BaseScraper):
    """Craigslist immobilier - Quebec / Montreal via sous-domaine regional."""

    source_key = "craigslist_immo_qc"
    use_brightdata = True

    def _base_url(self):
        key = (self.region or "quebec").lower().replace("é", "e").strip()
        if key in ("montreal", "laval"):
            return "https://montreal.craigslist.org"
        return "https://quebec.craigslist.org"

    def scrape(self):
        leads = []
        base = self._base_url()
        list_url = f"{base}/search/rea"
        html = self._safe_get(list_url)
        soup = self._soup(html)
        if not soup:
            return leads
        seen = set()
        for anchor in soup.select("a[href*='/rea/d/']"):
            href = (anchor.get("href") or "").split("?")[0].strip()
            if "/rea/d/" not in href:
                continue
            if href.startswith("/"):
                href = base + href
            if href in seen:
                continue
            seen.add(href)
            dhtml = self._safe_get(href)
            title = anchor.get_text(strip=True) or href.rsplit("/", 1)[-1]
            phone = self._find_phone(dhtml)
            if not phone:
                continue
            lead = self._lead(
                title,
                phone=phone,
                city=self.region,
                source_key=self.source_key,
                source_url=href,
            )
            if lead:
                leads.append(lead)
            if len(leads) >= 30:
                break
        return leads

