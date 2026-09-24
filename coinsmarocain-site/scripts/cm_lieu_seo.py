"""Title / description / robots des fiches /lieux — générés côté serveur.

Gabarit :
  Title : [Nom] — [mot-clé] [quartier/ville] | Coins Marocain
  Description : nom, type, quartier, prix « dès … » si connu, un différenciant.

noindex seulement si Privatisation seule (sans Découverte ni Hébergement)
ou page de preuve. Le gabarit SPA lieu.html reste noindex : ce n’est pas une fiche.
"""

from __future__ import annotations

import re


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _codes(lieu: dict) -> set[str]:
    codes = set(lieu.get("category_codes") or [])
    for c in lieu.get("categories") or []:
        if isinstance(c, dict) and c.get("code"):
            codes.add(c["code"])
    return codes


# Fiches en ligne pour validation humaine, pas encore à indexer.
PREVIEW_NOINDEX_SLUGS = {
    "la-casa-ysabella",
    "riad-la-casa-ysabella-marrakech",
    "riad-medina-marrakech-la-casa-ysabella",
}

# URL publique : {type}-{quartier_ou_ville}-{nom}. Interne Odoo reste le slug du nom.
PUBLIC_SLUGS = {
    "la-casa-ysabella": "riad-medina-marrakech-la-casa-ysabella",
    "riad-asrari": "riad-asrari-medina-marrakech",
}


def should_noindex(lieu: dict, *, proof: bool = False) -> bool:
    if proof:
        return True
    slug = (lieu.get("slug") or "").strip()
    if slug in PREVIEW_NOINDEX_SLUGS:
        return True
    codes = _codes(lieu)
    if "privatisation" in codes and not (codes & {"decouverte", "hebergement"}):
        return True
    return False


def place_phrase(lieu: dict) -> str:
    """Quartier réel + ville. Ne jamais inventer « Médina »."""
    district = (lieu.get("district") or "").strip()
    city = (lieu.get("city") or "Marrakech").strip()
    zone = (lieu.get("zone") or "").strip()
    if district.lower() == "bab doukala":
        district = "Bab Doukkala"
    if district:
        if city and city.lower() not in district.lower():
            return f"{district} {city}"
        return district
    if zone == "palmeraie":
        return "Palmeraie Marrakech"
    if zone == "agafay":
        return "désert d'Agafay"
    if zone == "marrakech_centre":
        return city or "Marrakech"
    return city or "Marrakech"


def keyword_principal(lieu: dict) -> str:
    name = (lieu.get("name") or "").lower()
    ptype = (lieu.get("property_type") or "").lower()
    text = strip_html(lieu.get("narrative_html") or lieu.get("description_html") or "").lower()
    blob = f"{name} {ptype} {text[:280]}"
    if "riad" in blob:
        return "Riad à louer"
    if "villa" in blob:
        return "Villa à louer"
    if "maison d'hôtes" in blob or "maison d’hôtes" in blob:
        return "Maison d'hôtes"
    if (lieu.get("pillar") or "") == "villas_riads":
        return "Maison à louer"
    return "Séjour à Marrakech"


def seo_title(lieu: dict) -> str:
    name = (lieu.get("name") or "Lieu").strip()
    return f"{name} — {keyword_principal(lieu)} {place_phrase(lieu)} | Coins Marocain"


def seo_description(lieu: dict) -> str:
    slug = (lieu.get("slug") or "").strip()
    if slug == "la-casa-ysabella":
        return (
            "Riad rénové au cœur de Bab Doukkala, patio et fontaine, "
            "chambres à thème dès 75$ CA/nuit. Réservation directe via Coins Marocain."
        )
    name = (lieu.get("name") or "Ce lieu").strip()
    kind = keyword_principal(lieu).replace(" à louer", "").lower()
    place = place_phrase(lieu)
    price = float(lieu.get("price_from") or 0)
    price_bit = f" dès {price:.0f}$ CA/nuit" if price else ""
    lede = strip_html(lieu.get("narrative_html") or lieu.get("description_html") or "")
    extra = ""
    if "piscine" in lede.lower():
        extra = " Piscine."
    elif "patio" in lede.lower() or "fontaine" in lede.lower():
        extra = " Patio."
    desc = (
        f"{name} — {kind} à {place}{price_bit}.{extra} "
        "Réservation directe via Coins Marocain."
    )
    return desc[:300]


def public_slug(lieu: dict) -> str:
    slug = (lieu.get("slug") or "").strip()
    return PUBLIC_SLUGS.get(slug, slug)


def seo_canonical(lieu: dict) -> str:
    return f"https://coinsmarocain.com/lieux/{public_slug(lieu)}"


def seo_bundle(lieu: dict, *, proof: bool = False) -> dict:
    return {
        "title": seo_title(lieu),
        "description": seo_description(lieu),
        "canonical": seo_canonical(lieu),
        "robots": "noindex,follow" if should_noindex(lieu, proof=proof) else "index,follow",
    }


# Titres visibles de galerie — gabarit {type} {quartier/ville} {nom}.
# Distinct du <title> document (seo_title) : ne pas y toucher.
YSABELLA_GALLERY_TITLE = "Riad médina Marrakech Casa Ysabella"
YSABELLA_GALLERY_SLUGS = {
    "la-casa-ysabella",
    "riad-la-casa-ysabella-marrakech",
    "riad-medina-marrakech-la-casa-ysabella",
}

_KIND_ARTICLES = {
    "Riad": ("du", "au"),
    "Villa": ("de la", "à la"),
    "Maison d'hôtes": ("de la", "à la"),
    "Maison": ("de la", "à la"),
    "Lieu": ("du", "au"),
}

_SECTION_HEADS = {
    "chambres": ("Chambres", "de"),
    "aires_communes": ("Aires communes", "de"),
    "restauration": ("Restauration", "a"),
    "exterieur_piscine": ("Extérieur et piscine", "de"),
    "bien_etre": ("Bien-être et spa", "de"),
}


def _is_ysabella(lieu: dict) -> bool:
    slug = (lieu.get("slug") or "").strip()
    return slug in YSABELLA_GALLERY_SLUGS or public_slug(lieu) in YSABELLA_GALLERY_SLUGS


def property_kind(lieu: dict) -> str:
    """Type court pour H2/H3 de galerie : Riad, Villa, Maison…"""
    name = (lieu.get("name") or "").lower()
    ptype = (lieu.get("property_type") or "").lower()
    text = strip_html(lieu.get("narrative_html") or lieu.get("description_html") or "").lower()
    blob = f"{name} {ptype} {text[:280]}"
    if "riad" in blob:
        return "Riad"
    if "villa" in blob:
        return "Villa"
    if "maison d'hôtes" in blob or "maison d’hôtes" in blob:
        return "Maison d'hôtes"
    if (lieu.get("pillar") or "") == "villas_riads":
        return "Maison"
    return "Lieu"


def gallery_place_phrase(lieu: dict) -> str:
    """Quartier/ville du H2 galerie. Ysabella : médina Marrakech (phrase Karine)."""
    if _is_ysabella(lieu):
        return "médina Marrakech"
    return place_phrase(lieu)


YSABELLA_H1 = "La Casa Ysabella — Riad médina Marrakech"
YSABELLA_LEDE = (
    "La Casa Ysabella est un riad de la médina de Marrakech, à Bab Doukkala : "
    "patio et fontaine, chambres dès 75 $ CA la nuit."
)
YSABELLA_ROOMS_H2 = "Chambres du riad La Casa Ysabella à Marrakech"


def page_h1(lieu: dict) -> str:
    """H1 visible. Ysabella : nom + mot-clé riad médina Marrakech."""
    if _is_ysabella(lieu):
        return YSABELLA_H1
    return (lieu.get("name") or "Lieu").strip()


def page_lede(lieu: dict) -> str:
    """Chapô sous le H1. Ysabella : riad, médina, Marrakech, Casa Ysabella."""
    if _is_ysabella(lieu):
        return YSABELLA_LEDE
    return ""


def rooms_h2_title(lieu: dict) -> str:
    """H2 de la section chambres."""
    if _is_ysabella(lieu):
        return YSABELLA_ROOMS_H2
    return "Les chambres"


def gallery_h2_title(lieu: dict) -> str:
    """Titre visible de la galerie. Gabarit {type} {quartier/ville} {nom}."""
    if _is_ysabella(lieu):
        return YSABELLA_GALLERY_TITLE
    kind = property_kind(lieu)
    place = gallery_place_phrase(lieu)
    name = (lieu.get("name") or "Lieu").strip()
    return re.sub(r"\s+", " ", f"{kind} {place} {name}").strip()


def gallery_h2_subtitle(lieu: dict, n_photos: int) -> str:
    """Sous-titre discret (nombre + thèmes)."""
    n = int(n_photos or 0)
    if _is_ysabella(lieu):
        return f"{n} photos — chambres, patio, table"
    return f"{n} photos"


def gallery_section_heading(code: str, lieu: dict, fallback: str = "") -> str:
    """H3 de section : « Chambres du riad {nom} à {ville} »."""
    spec = _SECTION_HEADS.get(code)
    if not spec:
        return fallback or code
    noun, art_key = spec
    kind = property_kind(lieu)
    de_art, a_art = _KIND_ARTICLES.get(kind, ("du", "au"))
    art = a_art if art_key == "a" else de_art
    name = (lieu.get("name") or "ce lieu").strip()
    city = (lieu.get("city") or "Marrakech").strip() or "Marrakech"
    return f"{noun} {art} {kind.lower()} {name} à {city}"
