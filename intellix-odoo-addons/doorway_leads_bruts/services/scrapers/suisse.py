# -*- coding: utf-8 -*-
import urllib.parse

from ..base_scraper import BaseScraper


class LocalChScraper(BaseScraper):
    source_key = "local_ch"

    def scrape(self):
        leads = []
        url = (
            "https://www.local.ch/fr/q"
            f"?what={urllib.parse.quote(self.mot_cle)}"
            f"&where={urllib.parse.quote(self.region)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select(".result, .entry, article"):
            name_el = card.select_one("h2, h3, .title")
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


class SearchChScraper(BaseScraper):
    source_key = "search_ch"

    def scrape(self):
        leads = []
        url = (
            "https://www.search.ch/tel/"
            f"?query={urllib.parse.quote(self.mot_cle)}"
            f"&place={urllib.parse.quote(self.region)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for row in soup.select("tr, .result, li"):
            name_el = row.select_one("a, td:first-child, .name")
            if not name_el:
                continue
            lead = self._lead(
                name_el.get_text(strip=True),
                phone=row.get_text(),
                city=self.region,
                source_key=self.source_key,
                source_url=url,
            )
            if lead:
                leads.append(lead)
        return leads
