# -*- coding: utf-8 -*-
import urllib.parse

from ..base_scraper import BaseScraper


class GoldenPagesBeScraper(BaseScraper):
    source_key = "goldenpages_be"

    def scrape(self):
        leads = []
        url = (
            "https://www.goldenpages.be/q/business/advanced/"
            f"where/{urllib.parse.quote(self.region)}"
            f"/what/{urllib.parse.quote(self.mot_cle)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select(".result, .listing, article"):
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


class InfobelBeScraper(BaseScraper):
    source_key = "infobel_be"

    def scrape(self):
        leads = []
        url = (
            f"https://www.infobel.com/fr/belgium/"
            f"{urllib.parse.quote(self.mot_cle)}/{urllib.parse.quote(self.region)}"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select(".result, .company, li"):
            name_el = card.select_one("h2, h3, a")
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


class DeuxiemeMainBeScraper(BaseScraper):
    source_key = "2ememain_be"

    def scrape(self):
        leads = []
        url = (
            f"https://www.2ememain.be/q/{urllib.parse.quote(self.mot_cle)}"
            f"/{urllib.parse.quote(self.region)}/Services/"
        )
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for ad in soup.select("article, .listing, li"):
            title = ad.select_one("h2, h3, a")
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
