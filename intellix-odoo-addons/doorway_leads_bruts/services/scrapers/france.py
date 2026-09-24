# -*- coding: utf-8 -*-
import logging
import urllib.parse

from ..base_scraper import BaseScraper

_logger = logging.getLogger(__name__)


class PagesJaunesFrScraper(BaseScraper):
    source_key = "pagesjaunes_fr"

    def scrape(self):
        leads = []
        for page in range(1, self.max_pages + 1):
            url = (
                "https://www.pagesjaunes.fr/annuaire/chercherlespros"
                f"?quoiqui={urllib.parse.quote(self.mot_cle)}"
                f"&ou={urllib.parse.quote(self.region)}&page={page}"
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            for card in soup.select(".bi-content, .result-item"):
                name_el = card.select_one("h3.bi-denomination, h3, .bi-denomination")
                phone_el = card.select_one(".bi-phone, .num-tel")
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


class SocieteComScraper(BaseScraper):
    source_key = "societe_com"

    def scrape(self):
        leads = []
        url = (
            "https://www.societe.com/cgi-bin/search"
            f"?champs={urllib.parse.quote(self.mot_cle)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for row in soup.select("tr.res, .result-table tr, .table tr"):
            name_el = row.select_one("a, td:first-child")
            if not name_el:
                continue
            lead = self._lead(
                name_el.get_text(strip=True),
                address=row.get_text(),
                city=self.region,
                source_key=self.source_key,
                source_url=url,
            )
            if lead:
                leads.append(lead)
        return leads


class LeBonCoinServicesScraper(BaseScraper):
    source_key = "leboncoin_fr"

    def scrape(self):
        leads = []
        for page in range(1, self.max_pages + 1):
            url = (
                "https://www.leboncoin.fr/recherche"
                f"?text={urllib.parse.quote(self.mot_cle)}"
                f"&locations={urllib.parse.quote(self.region)}"
                "&category=services&page=" + str(page)
            )
            html = self._safe_get(url)
            soup = self._soup(html)
            if not soup:
                break
            for ad in soup.select("[data-qa-id='aditem_container'], article, .aditem"):
                title = ad.select_one("h2, [data-qa-id='aditem_title'], .title")
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


class KompassFrScraper(BaseScraper):
    source_key = "kompass_fr"

    def scrape(self):
        leads = []
        url = (
            "https://fr.kompass.com/searchCompany"
            f"?text={urllib.parse.quote(self.mot_cle)}&country=FR"
            f"&city={urllib.parse.quote(self.region)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select(".company-container, .product-list-item, .list-result"):
            name_el = card.select_one("h2, .title, a.company-name")
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
