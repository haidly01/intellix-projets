# -*- coding: utf-8 -*-
"""Catalogue cross-sell villa (forfaits piscine + activités).

Affichage site = MAD ; Stripe = CAD (conversion via ICP coins_marocain.mad_per_cad).
`unit`:
  - person → prix × nombre de voyageurs
  - group  → prix fixe pour le groupe (indépendant du nb de voyageurs)
"""

# Affichage site = MAD ; Stripe = CAD
CROSS_SELL_PACKS = (
    # --- Forfaits piscine (source de vérité = page /forfaits, /pers) ---
    {
        "code": "acces_piscine",
        "group": "forfait",
        "unit": "person",
        "name": "Accès Piscine",
        "description": "Accès piscine et transat dans l'une de nos villas partenaires.",
        "price_mad": 180.0,
    },
    {
        "code": "formule_detente",
        "group": "forfait",
        "unit": "person",
        "name": "Formule Détente",
        "description": "Accès piscine + transat + déjeuner ou dîner sur place.",
        "price_mad": 390.0,
    },
    {
        "code": "formule_premium",
        "group": "forfait",
        "unit": "person",
        "name": "Formule Massage Premium",
        "description": "Accès piscine + repas + massage / bien-être (Zen Traitements).",
        "price_mad": 720.0,
    },
    {
        "code": "sunset_exclusif",
        "group": "forfait",
        "unit": "person",
        "name": "Sunset Exclusif",
        "description": "Fin d'après-midi jusqu'en soirée, dîner léger face au coucher de soleil. 16h-23h.",
        "price_mad": 590.0,
    },
    {
        "code": "zen_massage_carte",
        "group": "bienetre",
        "unit": "person",
        "name": "Massage / soin à la carte (Zen)",
        "description": "Soin à domicile Zen Traitements — dès 250 DH (kobido, dos, jambes…). Voir grille complète sur Partenaires.",
        "price_mad": 250.0,
    },
    {
        "code": "zen_relaxant_60",
        "group": "bienetre",
        "unit": "person",
        "name": "Massage relaxant 60 min (Zen)",
        "description": "Massage relaxant 60 min à domicile — Zen Traitements.",
        "price_mad": 400.0,
    },
    {
        "code": "zen_pierres_chaudes",
        "group": "bienetre",
        "unit": "person",
        "name": "Massage pierres chaudes (Zen)",
        "description": "Massage pierres chaudes 1h15 — Zen Traitements à domicile.",
        "price_mad": 650.0,
    },
    # --- Activités / excursions (prix / voyageur) ---
    {
        "code": "act_agafay_diner",
        "group": "activite",
        "unit": "person",
        "name": "Dîner désert Agafay + chameau",
        "description": "Dîner dans le désert d'Agafay avec promenade en chameau — départ Marrakech.",
        "price_mad": 360.0,
    },
    {
        "code": "act_agafay_sunset",
        "group": "activite",
        "unit": "person",
        "name": "Coucher de soleil Agafay",
        "description": "Excursion au coucher du soleil dans le désert d'Agafay.",
        "price_mad": 650.0,
    },
    {
        "code": "act_agafay_quad",
        "group": "activite",
        "unit": "person",
        "name": "Quad Agafay + déjeuner",
        "description": "Journée désert d'Agafay en quad avec déjeuner.",
        "price_mad": 1400.0,
    },
    {
        "code": "act_ourika",
        "group": "activite",
        "unit": "person",
        "name": "Vallée de l'Ourika",
        "description": "Excursion Ourika, cascades & Atlas — journée depuis Marrakech.",
        "price_mad": 200.0,
    },
    {
        "code": "act_atlas_vallees",
        "group": "activite",
        "unit": "person",
        "name": "Atlas & 5 vallées (privé)",
        "description": "Visite privée des montagnes de l'Atlas et des 5 vallées.",
        "price_mad": 1400.0,
    },
    {
        "code": "act_medina",
        "group": "activite",
        "unit": "person",
        "name": "Médina — Bahia, souks & guide",
        "description": "Visite privée des points forts : palais Bahia, souks et médina.",
        "price_mad": 600.0,
    },
    {
        "code": "act_cuisine",
        "group": "activite",
        "unit": "person",
        "name": "Cours de cuisine marocaine",
        "description": "Cours de cuisine avec une famille locale à Marrakech.",
        "price_mad": 360.0,
    },
    {
        "code": "act_quad_atlas",
        "group": "activite",
        "unit": "person",
        "name": "Quad Atlas (2 h)",
        "description": "Deux heures d'excursion en quad au cœur des montagnes de l'Atlas.",
        "price_mad": 510.0,
    },
)

PACKS_BY_CODE = {p["code"]: p for p in CROSS_SELL_PACKS}

GROUP_LABELS = {
    "forfait": "Forfaits piscine",
    "bienetre": "Massage & soins (Zen)",
    "activite": "Activités & excursions",
}
