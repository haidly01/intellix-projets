# -*- coding: utf-8 -*-
"""Catégorisation + textes public/privé — branché sur Claude déjà utilisé.

Ne change pas le scoring. Un second appel JSON via le même _call_claude_json.
"""
from __future__ import annotations

import json
import logging

_logger = logging.getLogger(__name__)

VERTICALS = {
    "coins_marocain": {
        "label": "Coins Marocain",
        "categories": [
            "demande_experience",
            "organisateur_evenement",
            "besoin_corporate",
            "proprietaire_riad",
            "avis_retour",
        ],
        "qualify": "dates, nombre de personnes, budget",
    },
    "coins_quebec": {
        "label": "Coins Québec",
        "categories": [
            "demande_experience",
            "organisateur_evenement",
            "avis_retour",
        ],
        "qualify": "dates, volume, budget",
    },
    "reno_immo_qc": {
        "label": "Réno / immo Québec",
        "categories": [
            "recherche_entrepreneur",
            "recherche_courtier",
            "avis_retour",
        ],
        "qualify": "nature du besoin (toiture, rénovation, courtier) et urgence",
    },
}

PARTNER_CATEGORIES = {"proprietaire_riad"}

RENO_BRANCHES = {
    "soumission_entrepreneurs",
    "soumission_toitures",
    "ici_thermopompe",
    "isolation_qc",
    "portes_fenetres",
    "maison_recherchee",
}

FALLBACK = {
    "coins_marocain": {
        "demande_experience": (
            "On propose justement ce type d'expérience sur mesure au Maroc. "
            "Je vous envoie un message privé avec quelques options.",
            "Bonjour, merci pour votre message. Vous cherchez pour combien de "
            "personnes et quelles dates environ ? Je peux vous proposer 2-3 options "
            "adaptées à votre budget — un numéro ou un créneau d'appel m'aide à aller vite.",
        ),
        "organisateur_evenement": (
            "On organise ce genre d'événements au Maroc. Je vous écris en privé "
            "pour caler les dates et le format.",
            "Bonjour, pour vous proposer un format adapté : combien de personnes, "
            "quelles dates, et un budget approximatif ? Un appel de 10 min suffit "
            "souvent — quel numéro vous va ?",
        ),
        "besoin_corporate": (
            "On accompagne les groupes corporate au Maroc. Je vous envoie les "
            "options en message privé.",
            "Bonjour, pour un besoin corporate : taille du groupe, dates, et "
            "budget cible ? Je peux bloquer un appel aujourd'hui si vous me "
            "laissez un numéro.",
        ),
        "proprietaire_riad": (
            "On travaille avec des riads sur la visibilité et les réservations "
            "(IntelliX). Je vous écris en privé.",
            "Bonjour, je vois que vous tenez un riad. On aide des propriétaires "
            "à remplir leur calendrier via Coins Marocain + IntelliX. Ça vous "
            "dirait d'en parler 10 minutes ? Quel numéro vous convient ?",
        ),
        "avis_retour": (
            "Merci pour le retour — je vous écris en privé pour en discuter "
            "sans encombrer le fil.",
            "Bonjour, merci pour votre message. On aimerait comprendre votre "
            "expérience et voir si on peut aider. Un numéro pour un court appel ?",
        ),
    },
    "coins_quebec": {
        "demande_experience": (
            "On a des expériences dans ce style au Québec. Je vous envoie un "
            "privé avec 2-3 pistes.",
            "Bonjour, pour vous proposer quelque chose de juste : combien de "
            "personnes, quelles dates, et un budget approximatif ? Un numéro "
            "ou un créneau d'appel m'aide à revenir vite.",
        ),
        "organisateur_evenement": (
            "On accompagne ce type d'événement au Québec. Je vous écris en privé.",
            "Bonjour, pour caler une proposition : dates, taille du groupe, "
            "budget ? Je peux vous appeler aujourd'hui si vous me laissez un numéro.",
        ),
        "avis_retour": (
            "Merci pour le partage — je vous écris en privé pour en parler.",
            "Bonjour, on aimerait comprendre votre expérience. Un numéro pour "
            "un court appel cette semaine ?",
        ),
    },
    "reno_immo_qc": {
        "recherche_entrepreneur": (
            "On a un entrepreneur dispo dans le secteur, je vous écris en privé.",
            "Bonjour, pour vous trouver le bon entrepreneur rapidement : quel "
            "est le problème exact, et êtes-vous disponible pour un appel "
            "aujourd'hui ?",
        ),
        "recherche_courtier": (
            "On peut vous mettre en lien avec un courtier du secteur. Je vous "
            "écris en privé.",
            "Bonjour, pour vous orienter : vous vendez, achetez, ou les deux ? "
            "Quel secteur, et un numéro pour un appel aujourd'hui ?",
        ),
        "avis_retour": (
            "Merci pour le retour — je vous écris en privé.",
            "Bonjour, on aimerait comprendre votre expérience. Un numéro pour "
            "un court appel ?",
        ),
    },
}

SYSTEM = (
    "Tu rédiges des réponses de veille sociale pour Agence Doorway. "
    "Réponds UNIQUEMENT en JSON valide. Jamais de prix. Jamais d'envoi automatique."
)


def vertical_for_branche(branche: str, explicit: str | None = None) -> str:
    if explicit in VERTICALS:
        return explicit
    if branche == "coins_marocain":
        return "coins_marocain"
    if branche in ("coins_quebec", "coins_commerce"):
        return "coins_quebec"
    if branche in RENO_BRANCHES:
        return "reno_immo_qc"
    return "reno_immo_qc"


def fallback_copy(vertical: str, categorie: str | None = None) -> dict:
    spec = VERTICALS.get(vertical) or VERTICALS["reno_immo_qc"]
    cat = categorie if categorie in spec["categories"] else spec["categories"][0]
    pair = (FALLBACK.get(vertical) or {}).get(cat) or next(iter(FALLBACK[vertical].values()))
    return {
        "categorie_lead": cat,
        "reponse_publique": pair[0],
        "message_prive": pair[1],
    }


def _parse_json(raw: str) -> dict:
    start = (raw or "").find("{")
    end = (raw or "").rfind("}") + 1
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def generate_lead_copy(scoring_service, signal, branche: str, categorie_lock: str | None = None) -> dict:
    """Génère categorie + 2 textes. categorie_lock = régénérer le texte seulement."""
    vertical = vertical_for_branche(
        branche,
        (getattr(signal, "plateforme", None) or "")
        if getattr(signal, "source", "") == "facebook_manuel"
        else None,
    )
    if getattr(signal, "source", "") == "facebook_manuel":
        plat = (signal.plateforme or "").strip()
        if plat in VERTICALS:
            vertical = plat
    spec = VERTICALS[vertical]
    locked = (categorie_lock or "").strip() or None
    if locked and locked not in spec["categories"]:
        locked = None

    content = (getattr(signal, "texte", None) or getattr(signal, "titre", None) or "")[:800]
    partner_note = (
        "Catégorie partenaire : ton partenariat/IntelliX, PAS une qualification client."
        if (locked in PARTNER_CATEGORIES or "proprietaire_riad" in spec["categories"])
        else ""
    )
    user = f"""
Signal (vertical {spec['label']}):
Titre: {getattr(signal, 'titre', '') or ''}
Texte: {content}
Source: {getattr(signal, 'source', '')}

Catégories autorisées: {', '.join(spec['categories'])}
{"Catégorie déjà choisie (ne pas changer): " + locked if locked else "Choisis UNE categorie_lead dans la liste."}
Qualification attendue dans le message privé: {spec['qualify']}.
{partner_note}

Règles:
- reponse_publique: 1 à 2 phrases, jamais de prix ni détail complet, annonce l'envoi d'un message privé.
- message_prive: qualifie le besoin et vise un numéro ou un RDV.
- Si categorie_lead est proprietaire_riad: explorer un partenariat IntelliX, pas une réservation.

JSON uniquement:
{{"categorie_lead": "...", "reponse_publique": "...", "message_prive": "..."}}
"""
    data = {}
    try:
        if scoring_service._claude_available():
            raw = scoring_service._call_claude_json(SYSTEM, user, max_tokens=500)
            data = _parse_json(raw)
    except Exception as err:  # noqa: BLE001
        _logger.info("lead_copy Claude failed: %s", err)
        data = {}

    fb = fallback_copy(vertical, locked or data.get("categorie_lead"))
    cat = locked or data.get("categorie_lead") or fb["categorie_lead"]
    if cat not in spec["categories"]:
        cat = fb["categorie_lead"]
    pub = (data.get("reponse_publique") or "").strip() or fb["reponse_publique"]
    priv = (data.get("message_prive") or "").strip() or fb["message_prive"]
    return {
        "categorie_lead": cat,
        "reponse_publique": pub,
        "message_prive": priv,
        "vertical": vertical,
    }


def apply_lead_copy_to_records(scoring_service, signal_records, infer_branche, regenerate_only=False):
    """Après le scoring (ou à la demande). N'écrit pas les scores."""
    count = 0
    errors = 0
    for rec in signal_records:
        try:
            branche = infer_branche(rec) if infer_branche else (rec.plateforme or "")
            lock = rec.categorie_lead if regenerate_only else None
            data = generate_lead_copy(scoring_service, rec, branche, categorie_lock=lock)
            vals = {
                "reponse_publique": data["reponse_publique"],
                "message_prive": data["message_prive"],
            }
            if not regenerate_only or not rec.categorie_lead:
                vals["categorie_lead"] = data["categorie_lead"]
            rec.sudo().write(vals)
            count += 1
        except Exception as err:  # noqa: BLE001
            errors += 1
            _logger.warning("lead_copy signal=%s failed: %s", rec.id, err)
            if not (rec.reponse_publique or "").strip() or not (rec.message_prive or "").strip():
                rec.sudo().write(
                    {
                        "reponse_publique": rec.reponse_publique
                        or "[Génération échouée] %s — relance depuis le tiroir."
                        % err,
                        "message_prive": rec.message_prive
                        or "[Génération échouée] Le texte privé n’a pas été produit. Relance « Régénérer la réponse ».",
                    }
                )
    return count
