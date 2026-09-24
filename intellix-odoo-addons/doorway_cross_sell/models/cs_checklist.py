# -*- coding: utf-8 -*-
"""Catalogue checklist cross-sell — hors ORM, testable sans Odoo."""

ORIGIN_VERTICALS = (
    "toiture",
    "thermopompe",
    "isolation",
    "portes_fenetres",
    "renovation_generale",
    "immobilier",
    "cuisine",
)

VARIABLE_TARGETS = (
    ("toiture", "Toiture"),
    ("isolation", "Isolation"),
    ("portes_fenetres", "Portes et fenêtres"),
    ("thermopompe", "Thermopompe"),
)

# source_id.name exact (après fold) — prioritaire sur Meta / description.
_SOURCE_LABEL_ORIGIN = {
    "cuisine": "cuisine",
    "reseau cuisine": "cuisine",
    "soumission toiture": "toiture",
    "ici thermopompe": "thermopompe",
    "isolation qc": "isolation",
    "portes et fenetres qc": "portes_fenetres",
    "soumission entrepreneurs": "renovation_generale",
    "maison recherchee": "immobilier",
    "maison recherchée": "immobilier",
}

# source_id / nom / domaine webhook → vertical.
_SOURCE_HINTS = (
    (("maison recherch", "maisonrecherchee", "facebook immobilier"), "immobilier"),
    (("reseaucuisine", "reseau cuisine", "cuisineqc"), "cuisine"),
    (("soumission toiture", "soumissiontoiture"), "toiture"),
    (("ici thermopompe", "icithermopompe", "thermopompe"), "thermopompe"),
    (("isolationqc", "isolation qc"), "isolation"),
    (
        ("portes et fenetre", "portesetfenetres", "portes-fenetres"),
        "portes_fenetres",
    ),
    (
        ("soumission entrepreneur", "soumissionentrepreneurs", "haidly"),
        "renovation_generale",
    ),
    (("toiture",), "toiture"),
    (("isolation",), "isolation"),
)

_CATEGORY_HINTS = (
    (("immobilier", "courtier immobilier"), "immobilier"),
    (("toiture",), "toiture"),
    (("thermopompe",), "thermopompe"),
    (("isolation",), "isolation"),
    (("portes et fenetre", "portes-fenetres", "fenetre"), "portes_fenetres"),
)

CS_BLOCKS = {
    "toiture": (
        {
            "key": "toiture_q1",
            "field": "cs_q_travaux_vente",
            "target": "immobilier",
        },
        {
            "key": "toiture_q2",
            "field": "cs_q_rachat_reno",
            "target": "portes_fenetres",
        },
        {
            "key": "toiture_q3",
            "field": "cs_q_autre_propriete",
            "target": "renovation_generale",
        },
    ),
    "thermopompe": (
        {
            "key": "thermo_q1",
            "field": "cs_q_travaux_vente",
            "target": "isolation",
        },
        {
            "key": "thermo_q2",
            "field": "cs_q_rachat_reno",
            "target": "renovation_generale",
        },
        {
            "key": "thermo_q3",
            "field": "cs_q_autre_propriete",
            "target": "immobilier",
        },
    ),
    "isolation": (
        {
            "key": "iso_q1",
            "field": "cs_q_travaux_vente",
            "target": "thermopompe",
        },
        {
            "key": "iso_q2",
            "field": "cs_q_rachat_reno",
            "target": "immobilier",
        },
        {
            "key": "iso_q3",
            "field": "cs_q_autre_propriete",
            "target": "renovation_generale",
        },
    ),
    "portes_fenetres": (
        {
            "key": "pf_q1",
            "field": "cs_q_travaux_vente",
            "target": "renovation_generale",
        },
        {
            "key": "pf_q2",
            "field": "cs_q_rachat_reno",
            "target": "toiture",
        },
        {
            "key": "pf_q3",
            "field": "cs_q_autre_propriete",
            "target": "immobilier",
        },
    ),
    "renovation_generale": (
        {
            "key": "reno_q1",
            "field": "cs_q_travaux_vente",
            "target": "immobilier",
        },
        {
            "key": "reno_q2",
            "field": "cs_q_rachat_reno",
            "target": None,
            "target_field": "cs_q_target_vertical",
        },
        {
            "key": "reno_q3",
            "field": "cs_q_autre_propriete",
            "target": "courtier_hypothecaire",
        },
    ),
    "immobilier": (
        {
            "key": "travaux_vente",
            "field": "cs_q_travaux_vente",
            "target": "renovation_generale",
        },
        {
            "key": "rachat_reno",
            "field": "cs_q_rachat_reno",
            "target": "renovation_generale",
        },
        {
            "key": "autre_propriete",
            "field": "cs_q_autre_propriete",
            "target": "renovation_generale",
        },
    ),
    "cuisine": (
        {
            "key": "cuisine_q1",
            "field": "cs_q_travaux_vente",
            "target": "renovation_generale",
        },
        {
            "key": "cuisine_q2",
            "field": "cs_q_rachat_reno",
            "target": None,
            "target_field": "cs_q_target_vertical",
        },
        {
            "key": "cuisine_q3",
            "field": "cs_q_autre_propriete",
            "target": "courtier_hypothecaire",
        },
    ),
}

CHECKLIST_COPY = {
    "toiture": {
        "badge": "Origine : Toiture",
        "title": "Questions à poser (soumissiontoitures.com)",
        "q1": "Ces travaux sont-ils faits en vue d'une vente prochaine ?",
        "to1": "→ Immobilier",
        "q2": "Avez-vous remarqué d'autres éléments à remplacer en même temps — fenêtres, portes ?",
        "to2": "→ Portes-fenêtres",
        "q3": "Envisagez-vous d'autres rénovations en parallèle ?",
        "to3": "→ Rénovation générale",
    },
    "thermopompe": {
        "badge": "Origine : Thermopompe",
        "title": "Questions à poser (icithermopompe.com)",
        "q1": "Votre facture de chauffage vous semble-t-elle élevée par rapport à la maison ?",
        "to1": "→ Isolation",
        "q2": "Ce changement s'inscrit-il dans un projet de rénovation plus large ?",
        "to2": "→ Rénovation générale",
        "q3": "Avez-vous un projet de vente ou d'achat en tête ?",
        "to3": "→ Immobilier",
    },
    "isolation": {
        "badge": "Origine : Isolation",
        "title": "Questions à poser (isolationqc.com)",
        "q1": "Avez-vous aussi des enjeux de confort ou de coûts de chauffage liés à cette zone ?",
        "to1": "→ Thermopompe",
        "q2": "Ces travaux sont-ils en prévision d'une vente ou d'un achat ?",
        "to2": "→ Immobilier",
        "q3": "Est-ce un projet isolé ou une rénovation plus large ?",
        "to3": "→ Rénovation générale",
    },
    "portes_fenetres": {
        "badge": "Origine : Portes et fenêtres",
        "title": "Questions à poser (portesetfenetresqc.com)",
        "q1": "Ce remplacement s'inscrit-il dans un agrandissement ou une construction ?",
        "to1": "→ Rénovation générale",
        "q2": "Avez-vous remarqué l'état de votre toiture en même temps ?",
        "to2": "→ Toiture",
        "q3": "Ces travaux sont-ils en vue d'une vente prochaine ?",
        "to3": "→ Immobilier",
    },
    "renovation_generale": {
        "badge": "Origine : Rénovation générale",
        "title": "Questions à poser (soumissionentrepreneurs.com)",
        "q1": "Ce projet est-il en vue d'une vente future de la propriété ?",
        "to1": "→ Immobilier",
        "q2": "Avez-vous identifié des besoins spécifiques pendant les travaux — toiture, isolation, portes/fenêtres ?",
        "to2": "→ le vertical mentionné",
        "q3": "Envisagez-vous de financer une partie de ce projet par un refinancement hypothécaire ?",
        "to3": "→ Courtier hypothécaire",
    },
    "immobilier": {
        "badge": "Origine : Immobilier",
        "title": "Questions à poser (maisonrecherchee.com)",
        "q1": "Le client prévoit-il des travaux avant la vente (peinture, toiture, plomberie) ?",
        "to1": "→ Rénovation générale",
        "q2": "Le client rachète-t-il une propriété qui nécessite une évaluation ou des rénovations ?",
        "to2": "→ Rénovation générale",
        "q3": "Le client a-t-il une autre propriété (locative, chalet, résidence secondaire) qui pourrait nécessiter des travaux ?",
        "to3": "→ Rénovation générale",
    },
    "cuisine": {
        "badge": "Origine : Cuisine",
        "title": "Questions à poser (reseaucuisineqc.com)",
        "q1": "Ce projet cuisine s'inscrit-il dans une rénovation plus large ?",
        "to1": "→ Rénovation générale",
        "q2": "Avez-vous identifié d'autres besoins — toiture, isolation, portes/fenêtres ?",
        "to2": "→ le vertical mentionné",
        "q3": "Envisagez-vous de financer ce projet par un refinancement hypothécaire ?",
        "to3": "→ Courtier hypothécaire",
    },
}

SLOT_FIELDS = (
    "cs_q_travaux_vente",
    "cs_q_rachat_reno",
    "cs_q_autre_propriete",
)


def _fold(text):
    return " ".join((text or "").lower().replace("_", " ").split())


def _match_hints(blob, hints):
    text = _fold(blob)
    if not text:
        return None
    for needles, vertical in hints:
        if any(needle in text for needle in needles):
            return vertical
    return None


def infer_origin_vertical(
    name="",
    source_label="",
    category_names=(),
    is_meta=False,
    description="",
):
    """Déduit le vertical d'origine. source_id gagne sur Meta."""
    exact = _SOURCE_LABEL_ORIGIN.get(_fold(source_label))
    if exact:
        return exact
    from_source = _match_hints(
        " ".join(part for part in (name, source_label, description) if part),
        _SOURCE_HINTS,
    )
    if from_source:
        return from_source
    if is_meta:
        return "immobilier"
    from_cat = _match_hints(" ".join(category_names or ()), _CATEGORY_HINTS)
    if from_cat:
        return from_cat
    blob = " ".join(
        part
        for part in (
            name,
            source_label,
            " ".join(category_names or ()),
            description,
        )
        if part
    )
    from_name = _match_hints(blob, _SOURCE_HINTS)
    if from_name:
        return from_name
    return "renovation_generale"


def checklist_copy(origin_vertical):
    return CHECKLIST_COPY.get(origin_vertical) or CHECKLIST_COPY["renovation_generale"]


def checklist_items(origin_vertical):
    return CS_BLOCKS.get(origin_vertical) or CS_BLOCKS["renovation_generale"]


def resolve_item_target(item, target_value=None):
    if item.get("target"):
        return item["target"]
    if item.get("target_field"):
        return target_value or False
    return False
