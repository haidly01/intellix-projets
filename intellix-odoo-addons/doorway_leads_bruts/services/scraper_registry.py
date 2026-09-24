# -*- coding: utf-8 -*-
"""Registre code source → classe scraper."""
from .scrapers.belgique import DeuxiemeMainBeScraper, GoldenPagesBeScraper, InfobelBeScraper
from .scrapers.canada import (
    Canada411Scraper,
    CraigslistQcImmoScraper,
    KijijiCaScraper,
    KijijiImmoQcScraper,
    LespacImmoQcScraper,
    YellowPagesCaScraper,
    YelpCaScraper,
)
from .scrapers.common import GoogleMapsScraper
from .scrapers.espagne import MilanunciosScraper, PaginasAmarillasEsScraper
from .scrapers.france import (
    KompassFrScraper,
    LeBonCoinServicesScraper,
    PagesJaunesFrScraper,
    SocieteComScraper,
)
from .scrapers.maroc import (
    AvitoMaScraper,
    ExpressBazarMaScraper,
    JijiMaScraper,
    KerixMaScraper,
    KhidmatMaScraper,
    MarocAnnuaireScraper,
    MarocAnnoncesScraper,
    MoncallcenterMaScraper,
    TelecontactMaScraper,
)
from .scrapers.suisse import LocalChScraper, SearchChScraper
from .scrapers.tunisie import KeejobTnScraper, TunisieAnnonceScraper

SCRAPER_MAP = {
    "google_maps": GoogleMapsScraper,
    "avito_ma": AvitoMaScraper,
    "marocannuaire_org": MarocAnnuaireScraper,
    "marocannonces_com": MarocAnnoncesScraper,
    "telecontact_ma": TelecontactMaScraper,
    "kerix_ma": KerixMaScraper,
    "moncallcenter_ma": MoncallcenterMaScraper,
    "jiji_ma": JijiMaScraper,
    "expressbazar_ma": ExpressBazarMaScraper,
    "khidmat_ma": KhidmatMaScraper,
    "pagesjaunes_fr": PagesJaunesFrScraper,
    "societe_com": SocieteComScraper,
    "leboncoin_fr": LeBonCoinServicesScraper,
    "kompass_fr": KompassFrScraper,
    "yellowpages_ca": YellowPagesCaScraper,
    "canada411": Canada411Scraper,
    "kijiji_ca": KijijiCaScraper,
    "kijiji_immo_ca": KijijiImmoQcScraper,
    "lespac_immo_ca": LespacImmoQcScraper,
    "craigslist_immo_qc": CraigslistQcImmoScraper,
    "yelp_ca": YelpCaScraper,
    "goldenpages_be": GoldenPagesBeScraper,
    "infobel_be": InfobelBeScraper,
    "2ememain_be": DeuxiemeMainBeScraper,
    "local_ch": LocalChScraper,
    "search_ch": SearchChScraper,
    "paginasamarillas_es": PaginasAmarillasEsScraper,
    "milanuncios": MilanunciosScraper,
    "tunisie_annonce_tn": TunisieAnnonceScraper,
    "keejob_tn": KeejobTnScraper,
}


def get_scraper(source_code, mot_cle, region, rayon_km=10, max_pages=5, env=None):
    cls = SCRAPER_MAP.get(source_code)
    if not cls:
        return None
    if source_code == "google_maps" and env is not None:
        config = env["doorway.credit.config"].get_config()
        zone_pays = {
            "maroc": "Maroc",
            "france": "France",
            "belgique": "Belgique",
            "espagne": "Espagne",
            "suisse": "Suisse",
            "canada": "Canada",
            "usa": "United States",
            "tunisie": "Tunisia",
        }
        zone = env.context.get("zone_geographique") or "france"
        return cls(
            mot_cle,
            region,
            rayon_km=rayon_km,
            max_pages=max_pages,
            api_key=config.google_maps_api_key,
            pays=zone_pays.get(zone, "Maroc"),
        )
    return cls(mot_cle, region, rayon_km=rayon_km, max_pages=max_pages)


def scrape_source(source_code, mot_cle, region, rayon_km=10, max_pages=5, env=None):
    scraper = get_scraper(source_code, mot_cle, region, rayon_km, max_pages, env=env)
    if not scraper:
        return []
    try:
        return scraper.scrape()
    except Exception:
        return []
