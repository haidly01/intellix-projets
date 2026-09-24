# -*- coding: utf-8 -*-
"""Libellé de service (sites) → catégorie renovation.service.category.

Match exact d’abord, puis mots-clés. Noms cibles = ceux de
renovation_conciergerie/data/service_categories.xml.
"""
import re
import unicodedata

# Cible = nom exact de renovation.service.category
SERVICE_LABEL_TO_CATEGORY = {
    # soumissiontoitures.com (et variantes postées dans description)
    "toiture": "Toiture",
    "diagnostic de toiture": "Toiture",
    "inspection de toiture": "Toiture",
    "inspection toiture": "Toiture",
    "remplacement de toiture": "Toiture",
    "reparation de toiture": "Toiture",
    "réparation de toiture": "Toiture",
    "fuite de toit": "Toiture",
    "fuite toiture": "Toiture",
    "toit plat": "Toiture",
    "toiture plate": "Toiture",
    "bardeaux": "Toiture",
    "bardeau": "Toiture",
    "membrane": "Toiture",
    "membrane elastomere": "Toiture",
    "membrane élastomère": "Toiture",
    "couverture": "Toiture",
    "toiture residentielle": "Toiture",
    "toiture commerciale": "Toiture",
    # isolationqc.com / haidly
    "isolation": "Isolation",
    "isolation de l entretoit": "Isolation",
    "isolation de lentretoit": "Isolation",
    "isolation entretoit": "Isolation",
    "isolation grenier": "Isolation",
    "isolation murs": "Isolation",
    "isolation sous-sol": "Isolation",
    "isolation sous sol": "Isolation",
    "thermopompe": "Thermopompe",
    "pompe a chaleur": "Thermopompe",
    "portes et fenetres": "Portes et fenetres",
    "portes et fenêtres": "Portes et fenetres",
    "porte et fenetre": "Portes et fenetres",
    "fenetres": "Portes et fenetres",
    "fenêtres": "Portes et fenetres",
    "cuisine": "Cuisine et salle de bain",
    "salle de bain": "Cuisine et salle de bain",
    "cuisine et salle de bain": "Cuisine et salle de bain",
    "revetement": "Revetement",
    "revêtement": "Revetement",
    "fondations": "Fondations",
    "paysagement": "Paysagement",
    "terrasse": "Terrasse et balcon",
    "balcon": "Terrasse et balcon",
    "terrasse et balcon": "Terrasse et balcon",
    "planchers": "Planchers",
    "plomberie": "Plomberie",
    "electricite": "Electricite",
    "électricité": "Electricite",
    "peinture": "Peinture",
    "solaire": "Solaire",
    "chauffe-eau": "Chauffe-eau",
    "chauffe eau": "Chauffe-eau",
    "decontamination": "Décontamination",
    "décontamination": "Décontamination",
    "immobilier": "Immobilier",
    "courtier immobilier": "Courtier immobilier",
    "courtier hypothecaire": "Courtier hypothécaire",
    "courtier hypothécaire": "Courtier hypothécaire",
    "assurances": "Assurances",
}

_KEYWORD_RULES = (
    (("toiture", "toit plat", "bardeau", "elastomere", "élastomère"), "Toiture"),
    (("isolation", "entretoit", "grenier"), "Isolation"),
    (("thermopompe", "pompe a chaleur", "pompe à chaleur"), "Thermopompe"),
    (("fenetre", "fenêtre", "portes et"), "Portes et fenetres"),
    (("salle de bain", "cuisine"), "Cuisine et salle de bain"),
    (("revetement", "revêtement"), "Revetement"),
    (("fondation",), "Fondations"),
    (("paysag",), "Paysagement"),
    (("terrasse", "balcon"), "Terrasse et balcon"),
    (("plancher",), "Planchers"),
    (("plomber",), "Plomberie"),
    (("electric", "électri"), "Electricite"),
    (("peinture",), "Peinture"),
)


def normalize_service_label(value):
    text = unicodedata.normalize("NFKD", (value or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def map_service_label(value):
    """Retourne le nom de catégorie ou None."""
    raw = (value or "").strip()
    if not raw:
        return None
    key = normalize_service_label(raw)
    if not key:
        return None
    if key in SERVICE_LABEL_TO_CATEGORY:
        return SERVICE_LABEL_TO_CATEGORY[key]
    folded = {normalize_service_label(k): v for k, v in SERVICE_LABEL_TO_CATEGORY.items()}
    if key in folded:
        return folded[key]
    for needles, category in _KEYWORD_RULES:
        if any(n in key for n in needles):
            return category
    return None


def labels_from_text(text):
    """Extrait « Service: … » / listes depuis une description de formulaire."""
    found = []
    blob = text or ""
    for match in re.finditer(
        r"(?:service|services|type de travaux)\s*[:|]\s*([^\n|<]+)",
        blob,
        flags=re.IGNORECASE,
    ):
        found.append(match.group(1).strip())
    return found


def collect_service_labels(data):
    """Libellés bruts depuis le payload webhook + description."""
    labels = []
    raw = data.get("services") or data.get("service_category") or data.get("serviceType")
    if isinstance(raw, str):
        labels.extend(s.strip() for s in raw.split(",") if s.strip())
    elif isinstance(raw, (list, tuple)):
        labels.extend(str(s).strip() for s in raw if str(s).strip())
    for key in ("service", "service_name", "type_travaux"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            labels.append(val.strip())
        elif isinstance(val, (list, tuple)):
            labels.extend(str(s).strip() for s in val if str(s).strip())
    blob = " ".join(
        str(data.get(k) or "")
        for k in ("message", "description", "notes", "comment")
    )
    labels.extend(labels_from_text(blob))
    return labels
