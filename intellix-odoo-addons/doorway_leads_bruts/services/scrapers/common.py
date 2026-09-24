# -*- coding: utf-8 -*-
import logging
import time
import urllib.parse

import requests

from ..base_scraper import BaseScraper

_logger = logging.getLogger(__name__)


class GoogleMapsScraper(BaseScraper):
    """Google Maps Places API si clé configurée, sinon recherche HTML."""

    source_key = "google_maps"

    def __init__(self, mot_cle, region, rayon_km=10, max_pages=5, api_key=None, pays="Maroc"):
        super().__init__(mot_cle, region, rayon_km=rayon_km, max_pages=max_pages)
        self.api_key = (api_key or "").strip()
        self.pays = pays or "Maroc"

    def scrape(self):
        if self.api_key:
            leads = self._scrape_places_api()
            if leads:
                return leads
        return self._scrape_html_fallback()

    def _scrape_places_api(self):
        leads = []
        geo_url = "https://maps.googleapis.com/maps/api/geocode/json"
        try:
            geo_r = requests.get(
                geo_url,
                params={"address": f"{self.region}, {self.pays}", "key": self.api_key},
                timeout=15,
            ).json()
        except Exception as exc:
            _logger.warning("Google geocode failed: %s", exc)
            return leads

        if not geo_r.get("results"):
            return leads

        loc = geo_r["results"][0]["geometry"]["location"]
        lat, lng = loc["lat"], loc["lng"]
        radius = min(self.rayon_km * 1000, 50000)
        place_ids = {}
        keywords = [self.mot_cle, f"{self.mot_cle} {self.region}"]

        for kw in keywords:
            token = None
            for _ in range(min(self.max_pages, 3)):
                params = {
                    "key": self.api_key,
                    "location": f"{lat},{lng}",
                    "radius": radius,
                    "keyword": kw,
                    "language": "fr",
                }
                if token:
                    params["pagetoken"] = token
                    time.sleep(2.5)
                try:
                    data = requests.get(
                        "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                        params=params,
                        timeout=15,
                    ).json()
                    for place in data.get("results", []):
                        pid = place.get("place_id")
                        if pid and pid not in place_ids:
                            place_ids[pid] = place.get("name", "")
                    token = data.get("next_page_token")
                    if not token:
                        break
                except Exception as exc:
                    _logger.warning("Google nearby search failed: %s", exc)
                    break

        for pid, fallback_name in list(place_ids.items())[: self.max_pages * 20]:
            try:
                time.sleep(0.25)
                detail = requests.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "key": self.api_key,
                        "place_id": pid,
                        "fields": (
                            "name,formatted_phone_number,international_phone_number,"
                            "website,formatted_address,rating,user_ratings_total"
                        ),
                        "language": "fr",
                    },
                    timeout=15,
                ).json().get("result", {})
                name = detail.get("name") or fallback_name
                if not name:
                    continue
                lead = self._lead(
                    name,
                    phone=(
                        detail.get("international_phone_number")
                        or detail.get("formatted_phone_number")
                        or ""
                    ),
                    website=(detail.get("website") or "").split("?")[0].rstrip("/"),
                    address=detail.get("formatted_address", ""),
                    city=self.region,
                    source_key=self.source_key,
                    source_url=f"https://www.google.com/maps/place/?q=place_id:{pid}",
                )
                if lead:
                    lead["rating"] = detail.get("rating", 0)
                    lead["reviews"] = detail.get("user_ratings_total", 0)
                    leads.append(lead)
            except Exception as exc:
                _logger.warning("Google place details %s: %s", pid, exc)
        return leads

    def _scrape_html_fallback(self):
        leads = []
        query = f"{self.mot_cle} {self.region}".strip()
        url = "https://www.google.com/maps/search/" + urllib.parse.quote(query)
        html = self._safe_get(url)
        soup = self._soup(html)
        if not soup:
            return leads
        for card in soup.select("[data-result-index], .Nv2PK, .section-result"):
            name_el = card.select_one(".fontHeadlineSmall, h3, .section-result-title")
            if not name_el:
                continue
            phone_el = card.select_one("[data-item-id*='phone'], .section-result-phone")
            addr_el = card.select_one(".fontBodyMedium, .section-result-location")
            lead = self._lead(
                name_el.get_text(strip=True),
                phone=phone_el.get_text(strip=True) if phone_el else "",
                address=addr_el.get_text(strip=True) if addr_el else "",
                city=self.region,
                source_key=self.source_key,
                source_url=url,
            )
            if lead:
                leads.append(lead)
            if len(leads) >= self.max_pages * 20:
                break
        return leads
