# -*- coding: utf-8 -*-
"""Couverture ville/région + recouvrement de services — testable hors ORM."""
from .region_map import lead_region, regions_from_texts, service_keys_from_names
from .service_label_map import labels_from_text, map_service_label

VERTICAL_TO_CATEGORY = {
    "toiture": "Toiture",
    "isolation": "Isolation",
    "thermopompe": "Thermopompe",
    "portes_fenetres": "Portes et fenetres",
    "immobilier": "Immobilier",
    "cuisine": "Cuisine et salle de bain",
    "courtier_hypothecaire": "Courtier hypothécaire",
    "renovation_generale": "Renovation interieure",
}


def services_overlap(lead_names, partner_names):
    """Toiture recouvre aussi une fiche « rénovation extérieure »."""
    lead_keys = service_keys_from_names(lead_names)
    partner_keys = service_keys_from_names(partner_names)
    if lead_keys and partner_keys and lead_keys & partner_keys:
        return True
    folded_lead = {n.strip().lower() for n in (lead_names or []) if n}
    folded_partner = {n.strip().lower() for n in (partner_names or []) if n}
    return bool(folded_lead & folded_partner)


def partner_covers_city(lead_city, partner_city="", partner_city_text="", coverage_mode=""):
    """Longueuil est couvert par « Rive-Sud » / Montérégie, pas seulement le mot Longueuil."""
    city = (lead_city or "").strip()
    if coverage_mode == "province":
        return True
    if not city:
        return False
    lead_reg = lead_region(city)
    partner_regs = regions_from_texts(partner_city, partner_city_text)
    if lead_reg and lead_reg in partner_regs:
        return True
    needle = city.lower()
    blob = " ".join(part for part in (partner_city, partner_city_text) if part).lower()
    if needle and needle in blob:
        return True
    return False


def infer_category_names(source_label="", description="", lead_name=""):
    names = []
    for raw in (source_label, lead_name):
        mapped = map_service_label(raw)
        if mapped:
            names.append(mapped)
    for raw in labels_from_text(description or ""):
        mapped = map_service_label(raw)
        if mapped:
            names.append(mapped)
    if not names and description:
        mapped = map_service_label(description)
        if mapped:
            names.append(mapped)
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen
