# -*- coding: utf-8 -*-
import urllib.parse

from ..base_scraper import BaseScraper


class PaginasAmarillasEsScraper(BaseScraper):
    source_key = "paginasamarillas_es"

    def scrape(self):
        leads = []
        url = (
            f"https://www.paginasamarillas.es/search/"
            f"{urllib.parse.quote(self.mot_cle)}/all-ma/all-pr/"
            f"{urllib.parse.quote(self.region)}/"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select(".listado-item, .result, article"):
            name_el = card.select_one("h2, h3, .nombre")
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


class MilanunciosScraper(BaseScraper):
    source_key = "milanuncios"

    def scrape(self):
        leads = []
        url = (
            f"https://www.milanuncios.com/servicios/"
            f"{urllib.parse.quote(self.mot_cle)}/?demanda=n"
            f"&donde={urllib.parse.quote(self.region)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for ad in soup.select(".aditem, article, li"):
            title = ad.select_one("h2, a, .title")
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
