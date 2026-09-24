# -*- coding: utf-8 -*-
"""Données d’exploitation Mon Coin (analytique, stock, staff, boutique, fidélité).

En démo : scénario Café des Trois Rives (maquette), isolé de la fiche partenariat.
Hors démo : identité réelle + états vides tant que caisse / téléphone ne sont pas branchés.
"""
from __future__ import annotations

from datetime import date, timedelta

try:
    from markupsafe import Markup
except ImportError:  # pragma: no cover
    Markup = str


_MOIS = (
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _today_label() -> str:
    d = date.today()
    return "Aujourd'hui, %s %s" % (d.day, _MOIS[d.month])


def _week_headers() -> tuple[list[str], int]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    names = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")
    labels = []
    today_idx = 0
    for i in range(7):
        day = monday + timedelta(days=i)
        labels.append("%s %s" % (names[i], day.day))
        if day == today:
            today_idx = i
    return labels, today_idx


def _region_label(rec) -> str:
    if not rec:
        return "Québec"
    sel = dict(rec._fields["region"].selection)
    return sel.get(rec.region) or rec.city or "Québec"


def portal_ops_payload(rec) -> dict:
    if rec and rec.is_demo:
        return _demo_cafe_ops()
    return _live_ops(rec)


def _live_ops(rec) -> dict:
    name = rec.name if rec else "Mon commerce"
    return {
        "has_ops": False,
        "merchant": name,
        "place": "%s · Commerçant" % _region_label(rec),
        "today": _today_label(),
        "briefing": (
            "Branchez le téléphone d’affaires et le terminal de paiement "
            "pour voir le briefing, le journal d’appels et les vedettes."
        ),
        "calls_7d": rec.pin_view_count or 0 if rec else 0,
        "avg_duration": "—",
        "conv_rate": "—",
        "missed": 0,
        "quality": "—",
        "ca_today": "—",
        "ca_delta": "",
        "ticket": "—",
        "tx": rec.reservation_public_count or 0 if rec else 0,
        "ca_source": "En attente du terminal",
        "vedettes": [],
        "frise": [],
        "boost_left": None,
        "calls": [],
        "review_count": 0,
        "stock": [],
        "alerts": [],
        "week_days": _week_headers()[0],
        "week_today": _week_headers()[1],
        "shifts": [],
        "catalog": [],
        "staff_perf": [],
        "clock": [],
        "channels": [
            {"mark": "A", "name": "Amazon.ca", "detail": "Non activé", "status": "locked", "status_label": "Disponible"},
            {"mark": "E", "name": "Etsy", "detail": "Non activé", "status": "locked", "status_label": "Disponible"},
            {"mark": "F", "name": "Facebook Marketplace", "detail": "Non activé", "status": "locked", "status_label": "Disponible"},
        ],
        "orders": [],
        "fid_query": "",
        "fid": None,
        "fid_hist": [],
    }


def _demo_cafe_ops() -> dict:
    return {
        "has_ops": True,
        "merchant": "Café des Trois Rives",
        "place": "Sorel-Tracy · Commerçant",
        "today": _today_label(),
        "briefing": Markup(
            "<b>18 appels</b> hier, taux de conversion de <b>31%</b>. "
            "Le <b>mardi</b> reste votre jour le plus creux cette semaine. "
            "<b>2 appels</b> ont été signalés qualité faible — à revoir dans le journal ci-dessous."
        ),
        "calls_7d": 112,
        "avg_duration": "3:42",
        "conv_rate": "34%",
        "missed": 9,
        "quality": "Bon",
        "ca_today": "1 284 $",
        "ca_delta": "▲ 6% vs hier",
        "ca_delta_up": True,
        "ticket": "22,60 $",
        "tx": 57,
        "ca_source": "Terminal de paiement",
        "vedettes": [
            {"rank": 1, "name": "Café en grain — mélange maison", "units": "29 unités · SKU CQ-CAF-001", "rev": "312,00 $", "delta": "▲ 14%", "up": True},
            {"rank": 2, "name": "Confiture locale — pot 250ml", "units": "19 unités · SKU CQ-CON-008", "rev": "142,50 $", "delta": "▲ 5%", "up": True},
            {"rank": 3, "name": "Tasse en grès signature", "units": "8 unités · SKU CQ-TAS-014", "rev": "144,00 $", "delta": "▼ 3%", "up": False},
            {"rank": 4, "name": "Croissant aux amandes", "units": "41 unités · SKU CQ-CRO-003", "rev": "123,00 $", "delta": "▲ 8%", "up": True},
            {"rank": 5, "name": "Miel de la Montérégie", "units": "7 unités · SKU CQ-MIE-021", "rev": "84,00 $", "delta": "▼ 2%", "up": False},
        ],
        "frise": [
            {"left": 8, "src": "search"},
            {"left": 14, "src": "site"},
            {"left": 22, "src": "search"},
            {"left": 33, "src": "radio"},
            {"left": 36, "src": "radio"},
            {"left": 40, "src": "radio"},
            {"left": 47, "src": "social"},
            {"left": 55, "src": "site"},
            {"left": 63, "src": "search"},
            {"left": 71, "src": "itex"},
            {"left": 80, "src": "site"},
            {"left": 85, "src": "boutique"},
            {"left": 88, "src": "search"},
        ],
        "boost_left": 32,
        "boost_label": "Boost — capsule radio 07:40",
        "calls": [
            {
                "time": "08:12",
                "src": "radio",
                "src_label": "Radio",
                "dur": "2:14",
                "result": "Renseignement",
                "quality": "faible",
                "quality_label": "Faible",
                "review": True,
                "report": [
                    ("Accueil", "Correct, un peu rapide"),
                    ("Écoute", "Interrompt le client"),
                    ("Vente / upsell", "Non tentée"),
                    ("Résolution", "Partielle"),
                    ("Ton général", "Pressé"),
                ],
            },
            {
                "time": "09:03",
                "src": "site",
                "src_label": "SEA",
                "dur": "4:51",
                "result": "Réservation",
                "quality": "bon",
                "quality_label": "Bon",
                "review": False,
                "report": [
                    ("Accueil", "Chaleureux"),
                    ("Écoute", "Attentive"),
                    ("Vente / upsell", "Proposé, accepté"),
                    ("Résolution", "Complète"),
                    ("Ton général", "Naturel"),
                ],
            },
            {
                "time": "10:47",
                "src": "search",
                "src_label": "SEO",
                "dur": "1:38",
                "result": "Qualifié",
                "quality": "moyen",
                "quality_label": "Moyen",
                "review": False,
                "report": [],
            },
            {
                "time": "11:20",
                "src": "itex",
                "src_label": "ITEX",
                "dur": "0:52",
                "result": "Manqué",
                "quality": "faible",
                "quality_label": "Faible",
                "review": True,
                "report": [],
            },
            {
                "time": "13:05",
                "src": "social",
                "src_label": "Réseaux",
                "dur": "3:12",
                "result": "Réservation",
                "quality": "bon",
                "quality_label": "Bon",
                "review": False,
                "report": [],
            },
            {
                "time": "15:38",
                "src": "boutique",
                "src_label": "Boutique",
                "dur": "1:05",
                "result": "Qualifié",
                "quality": "bon",
                "quality_label": "Bon",
                "review": False,
                "report": [],
            },
        ],
        "review_count": 2,
        "stock": [
            {"sku": "CQ-CAF-001", "name": "Café en grain — mélange maison", "cat": "Boisson", "flow": "4,2 u/j", "trend": "▲ 14% — vedette", "up": True, "qty": 9, "reorder": "7 jours", "badge": "faible", "badge_label": "Rupture ~2j", "bold": True},
            {"sku": "CQ-CON-008", "name": "Confiture locale — pot 250ml", "cat": "Épicerie fine", "flow": "2,8 u/j", "trend": "▲ 5% — vedette", "up": True, "qty": 14, "reorder": "10 jours", "badge": "moyen", "badge_label": "À surveiller", "bold": False},
            {"sku": "CQ-TAS-014", "name": "Tasse en grès signature", "cat": "Boutique", "flow": "1,1 u/j", "trend": "▼ 3%", "up": False, "qty": 22, "reorder": "14 jours", "badge": "bon", "badge_label": "Stable", "bold": False},
            {"sku": "CQ-CRO-003", "name": "Croissant aux amandes", "cat": "Pâtisserie", "flow": "5,8 u/j", "trend": "▲ 8% — vedette", "up": True, "qty": 18, "reorder": "Quotidien", "badge": "bon", "badge_label": "Stable", "bold": False},
            {"sku": "CQ-MIE-021", "name": "Miel de la Montérégie", "cat": "Épicerie fine", "flow": "0,9 u/j", "trend": "▼ 2%", "up": False, "qty": 16, "reorder": "21 jours", "badge": "bon", "badge_label": "Stable", "bold": False},
            {"sku": "CQ-SUC-011", "name": "Sucre d’érable 250ml", "cat": "Épicerie fine", "flow": "0,6 u/j", "trend": "▲ 1%", "up": True, "qty": 31, "reorder": "21 jours", "badge": "bon", "badge_label": "Stable", "bold": False},
        ],
        "alerts": [
            {
                "mark": "!",
                "motif": "Rupture prévue · vedette en hausse",
                "title": "Café en grain, mélange maison — SKU CQ-CAF-001",
                "text": (
                    "Au rythme actuel, le stock sera épuisé avant le prochain réassort typique "
                    "(~5 jours d'écart) — et c'est le produit vedette de la semaine (▲14 %), "
                    "donc la demande ne ralentit pas."
                ),
                "bar": 22,
                "actions": [
                    {"label": "Financer le réassort — Driven", "href": "/mon-coin/boosts?tab=driven", "gold": True},
                    {"label": "Booster les ventes du stock restant", "href": "/mon-coin/boosts?tab=radio", "gold": False},
                    {"label": "Échanger contre du stock — ITEX", "href": "/mon-coin/boosts?tab=itex", "gold": False},
                ],
            },
            {
                "mark": "D",
                "motif": "Motif Driven · besoin de stock",
                "title": "Réassort financé — ~1 200 $",
                "text": "25 sacs à 48 $ : fonds de roulement pour tenir 6 jours de plus sans casser la vedette.",
                "bar": None,
                "actions": [],
            },
            {
                "mark": "B",
                "motif": "Motif Boost · vendre le reste",
                "title": "Capsule radio + pin vedette",
                "text": "Si le réassort tarde : pousser les 9 sacs restants aujourd’hui plutôt que les laisser dormir en rayon.",
                "bar": None,
                "actions": [],
            },
            {
                "mark": "I",
                "motif": "Motif ITEX · capacité / troc",
                "title": "Échange contre du grain d’un torréfacteur du réseau",
                "text": "Le réassort peut passer par un échange plutôt qu’un financement ou une vente accélérée.",
                "bar": None,
                "actions": [],
            },
            {
                "mark": "↑",
                "motif": "Réassort anticipé · vedette",
                "title": "Confiture locale — SKU CQ-CON-008",
                "text": (
                    "Pas encore en rupture, mais la tendance est à la hausse (▲5 % sur 7 jours). "
                    "Commander avant le seuil d’alerte évite une rupture surprise."
                ),
                "bar": None,
                "actions": [
                    {"label": "Planifier le réassort", "href": "/mon-coin/inventaire", "gold": False},
                ],
            },
        ],
        "week_days": _week_headers()[0],
        "week_today": _week_headers()[1],
        "shifts": [
            {"name": "Sarah L.", "cells": ["7h–15h", "", "7h–15h", "7h–15h", "7h–15h", "", ""]},
            {"name": "Marc-Ant. B.", "cells": ["", "11h–19h", "11h–19h", "", "11h–19h", "9h–17h", ""]},
            {"name": "Julie P.", "cells": ["15h–21h", "15h–21h", "", "15h–21h", "", "9h–17h", "9h–15h"]},
        ],
        "staff_perf": [
            {"ini": "SL", "name": "Sarah L.", "detail": "24 appels traités cette semaine", "q": "bon", "q_label": "Bon"},
            {"ini": "MB", "name": "Marc-Ant. B.", "detail": "18 appels traités cette semaine", "q": "moyen", "q_label": "Moyen"},
            {"ini": "JP", "name": "Julie P.", "detail": "21 appels traités cette semaine", "q": "faible", "q_label": "Faible"},
        ],
        "clock": [
            {"ini": "SL", "name": "Sarah L.", "detail": "Arrivée 6:58", "late": False, "label": "À l'heure"},
            {"ini": "MB", "name": "Marc-Ant. B.", "detail": "Arrivée 11:16", "late": True, "label": "Retard 16 min"},
            {"ini": "JP", "name": "Julie P.", "detail": "Prévue 15h00", "late": False, "label": "À venir"},
        ],
        "channels": [
            {"mark": "A", "name": "Amazon.ca", "detail": "18 produits publiés", "threshold": "Seuil : 1 produit actif — atteint", "status": "connected", "status_label": "Connecté"},
            {"mark": "E", "name": "Etsy", "detail": "6 produits actuellement", "threshold": "Seuil : 10 produits actifs — non atteint", "status": "locked", "status_label": "Seuil non atteint"},
            {"mark": "F", "name": "Facebook Marketplace", "detail": "Non activé", "threshold": "Seuil : 5 produits actifs — 0 publié", "status": "wait", "status_label": "En attente"},
            {"mark": "B", "name": "bol.com", "detail": "3 produits en brouillon", "threshold": "Seuil : 20 produits actifs — non atteint", "status": "locked", "status_label": "Seuil non atteint"},
        ],
        "orders": [
            {"product": "Confiture locale ×3", "channel": "Amazon.ca", "amount": "34,50 $"},
            {"product": "Tasse en grès", "channel": "Amazon.ca", "amount": "18,00 $"},
            {"product": "Café en grain 500g", "channel": "Amazon.ca", "amount": "14,25 $"},
            {"product": "Miel de la Montérégie", "channel": "Amazon.ca", "amount": "12,00 $"},
        ],
        "catalog": [
            {"sku": "CQ-CAF-001", "name": "Café en grain", "amazon": "Publié", "amazon_cls": "ok", "etsy": "Non éligible", "etsy_cls": "no", "fb": "En pause", "fb_cls": "pause", "bol": "—", "bol_cls": "no"},
            {"sku": "CQ-CON-008", "name": "Confiture locale", "amazon": "Publié", "amazon_cls": "ok", "etsy": "Publié", "etsy_cls": "ok", "fb": "Non publié", "fb_cls": "no", "bol": "Brouillon", "bol_cls": "pause"},
            {"sku": "CQ-TAS-014", "name": "Tasse en grès", "amazon": "Publié", "amazon_cls": "ok", "etsy": "Publié", "etsy_cls": "ok", "fb": "Non publié", "fb_cls": "no", "bol": "Brouillon", "bol_cls": "pause"},
            {"sku": "CQ-MIE-021", "name": "Miel de la Montérégie", "amazon": "Publié", "amazon_cls": "ok", "etsy": "Publié", "etsy_cls": "ok", "fb": "Non publié", "fb_cls": "no", "bol": "Brouillon", "bol_cls": "pause"},
            {"sku": "CQ-CRO-003", "name": "Croissant aux amandes", "amazon": "Non éligible", "amazon_cls": "no", "etsy": "Non éligible", "etsy_cls": "no", "fb": "Non éligible", "fb_cls": "no", "bol": "Non éligible", "bol_cls": "no"},
        ],
        "fid_query": "marie-eve.t@gmail.com",
        "fid": {
            "ini": "MT",
            "name": "Marie-Ève T.",
            "since": "Cliente depuis mars 2026 · 6 achats",
            "points": "340 pts",
            "perk": "Rabais 10% dès 300 pts",
        },
        "fid_hist": [
            {"date": "12 août", "src": "En magasin", "amount": "46,00 $", "pts": "+18"},
            {"date": "3 août", "src": "Boutique en ligne", "amount": "28,50 $", "pts": "+11"},
            {"date": "22 juillet", "src": "En magasin", "amount": "52,00 $", "pts": "+20"},
        ],
    }
