# -*- coding: utf-8 -*-
"""Service Claude (Anthropic) — génération d'un PLAN DE SITE en JSON strict.

À partir d'un brief (inspiration / personas / objectifs / ton / secteur / pages)
et, en itération, du plan précédent + une instruction, Claude renvoie un plan
structuré : pages → sections ordonnées → copy + palette + SEO.

Conçu pour ÉCHOUER PROPREMENT : clé absente, réseau, HTTP, JSON invalide →
renvoie ``(None, message_utilisateur)`` sans jamais lever.
"""
import json
import logging

import requests

from . import config_loader

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MODEL_PARAM = "doorway_site_builder.claude_model"

# Types de sections compris par le générateur (cf. services/snippets.py).
ALLOWED_SECTION_TYPES = [
    "hero", "about", "features", "services", "numbers",
    "testimonials", "pricing", "contact", "cta",
]

MAX_PAGES = 6
MAX_SECTIONS_PER_PAGE = 8

SYSTEM_PROMPT = (
    "Tu es une directrice artistique et conceptrice-rédactrice web senior. "
    "Tu conçois des sites vitrines clairs, modernes et orientés conversion. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte autour, "
    "sans préambule, sans backticks."
)


def get_model(env):
    icp = env["ir.config_parameter"].sudo()
    return (icp.get_param(MODEL_PARAM) or DEFAULT_MODEL).strip()


def is_available(env):
    return config_loader.is_available(env)


def _build_user_prompt(brief, previous_plan=None, instruction=None):
    """Construit le message utilisateur (brief + éventuelle itération)."""
    schema = {
        "site_name": "string",
        "tone": "string (ex: premium, chaleureux, corporate)",
        "palette": {
            "primary": "#RRGGBB",
            "secondary": "#RRGGBB",
            "accent": "#RRGGBB",
            "background": "#RRGGBB",
            "text": "#RRGGBB",
        },
        "assistant_message": "court message récapitulatif adressé au client (1-3 phrases, style conseiller)",
        "pages": [
            {
                "title": "Accueil",
                "slug": "accueil",
                "is_home": True,
                "in_menu": True,
                "seo_title": "titre SEO < 60 caractères",
                "seo_description": "meta description < 160 caractères",
                "sections": [
                    {
                        "type": "|".join(ALLOWED_SECTION_TYPES),
                        "heading": "titre de section",
                        "subtitle": "sous-titre (optionnel)",
                        "body": "paragraphe (optionnel)",
                        "button_label": "libellé bouton (optionnel)",
                        "button_href": "/contactus ou # (optionnel)",
                        "items": [
                            {
                                "title": "titre item",
                                "text": "texte item",
                                "name": "nom (offres tarifaires)",
                                "price": "prix (tarifs)",
                                "period": "/ mois (tarifs)",
                                "features": ["ligne 1", "ligne 2"],
                                "quote": "citation (témoignages)",
                                "author": "auteur (témoignages)",
                                "role": "fonction (témoignages)",
                            }
                        ],
                        "email": "email (section contact)",
                        "phone": "téléphone (section contact)",
                        "address": "adresse (section contact)",
                    }
                ],
            }
        ],
    }

    parts = [
        "Conçois un PLAN DE SITE VITRINE complet à partir de ce brief client.",
        "",
        "BRIEF CLIENT :",
        json.dumps(brief, ensure_ascii=False, indent=2),
        "",
    ]

    if previous_plan:
        parts += [
            "PLAN ACTUEL (à faire ÉVOLUER, pas à repartir de zéro) :",
            json.dumps(previous_plan, ensure_ascii=False),
            "",
            "INSTRUCTION D'ITÉRATION DU CLIENT :",
            (instruction or "").strip() or "(améliore la cohérence générale)",
            "",
            "Réutilise les slugs de pages existants quand tu modifies une page "
            "existante, afin que la mise à jour ne crée pas de doublon.",
            "",
        ]

    parts += [
        "CONTRAINTES :",
        f"- Entre 3 et {MAX_PAGES} pages maximum. Toujours une page d'accueil "
        "(is_home=true) en première position.",
        "- Pages standard recommandées : Accueil, À propos, Services/Offre, "
        "Contact (et Tarifs si pertinent).",
        f"- Chaque page : 2 à {MAX_SECTIONS_PER_PAGE} sections ordonnées et cohérentes.",
        f"- 'type' de section STRICTEMENT dans : {', '.join(ALLOWED_SECTION_TYPES)}.",
        "- La page d'accueil commence par une section 'hero'.",
        "- La page Contact contient une section 'contact'.",
        "- 'slug' en minuscules, sans accents ni espaces (ex: 'a-propos').",
        "- Rédige TOUTE la copy dans la langue du brief (français par défaut), "
        "prête à publier, sans texte de remplacement type 'Lorem ipsum'.",
        "- Palette : couleurs hexadécimales cohérentes avec le ton et le secteur.",
        "",
        "Réponds STRICTEMENT avec un objet JSON respectant ce schéma "
        "(les clés d'item sont optionnelles selon le type) :",
        json.dumps(schema, ensure_ascii=False),
    ]
    return "\n".join(parts)


def _parse_json(raw):
    """Strip fences ```json puis json.loads sur le premier objet {...}."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        _logger.warning("Site builder : JSON Claude invalide")
        return None


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "oui", "vrai")
    return default


def _clean_section(section):
    if not isinstance(section, dict):
        return None
    stype = (section.get("type") or "").strip().lower()
    if not stype:
        return None
    section["type"] = stype
    items = section.get("items")
    if items is not None and not isinstance(items, list):
        section["items"] = []
    return section


def _clean_page(page, index):
    if not isinstance(page, dict):
        return None
    title = (page.get("title") or "").strip() or f"Page {index + 1}"
    slug = (page.get("slug") or "").strip().lower()
    raw_sections = page.get("sections")
    sections = []
    if isinstance(raw_sections, list):
        for sec in raw_sections[:MAX_SECTIONS_PER_PAGE]:
            cleaned = _clean_section(sec)
            if cleaned:
                sections.append(cleaned)
    if not sections:
        return None
    return {
        "title": title,
        "slug": slug,
        "is_home": _coerce_bool(page.get("is_home"), default=(index == 0)),
        "in_menu": _coerce_bool(page.get("in_menu"), default=True),
        "seo_title": (page.get("seo_title") or title)[:70],
        "seo_description": (page.get("seo_description") or "")[:200],
        "sections": sections,
    }


def validate_plan(plan):
    """Valide/normalise le plan. Renvoie (plan_clean | None, message)."""
    if not isinstance(plan, dict):
        return None, "Le plan renvoyé n'est pas un objet JSON exploitable."
    raw_pages = plan.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        return None, "Le plan ne contient aucune page exploitable."
    pages = []
    for idx, page in enumerate(raw_pages[:MAX_PAGES]):
        cleaned = _clean_page(page, idx)
        if cleaned:
            pages.append(cleaned)
    if not pages:
        return None, "Aucune page valide après validation du plan."
    # Garantir exactement une page d'accueil.
    if not any(p["is_home"] for p in pages):
        pages[0]["is_home"] = True
    else:
        seen_home = False
        for p in pages:
            if p["is_home"] and not seen_home:
                seen_home = True
            else:
                p["is_home"] = False
    palette = plan.get("palette")
    if not isinstance(palette, dict):
        palette = {}
    clean = {
        "site_name": (plan.get("site_name") or "Mon site").strip(),
        "tone": (plan.get("tone") or "").strip(),
        "palette": palette,
        "assistant_message": (plan.get("assistant_message") or "").strip(),
        "pages": pages,
    }
    return clean, "Plan généré."


def generate_plan(env, brief, previous_plan=None, instruction=None):
    """Appelle Claude et renvoie (plan_clean | None, message).

    :param brief: dict du brief client (inspiration, personas, objectifs…).
    :param previous_plan: plan précédent (dict) pour une itération.
    :param instruction: consigne d'itération en langage naturel.
    """
    api_key = config_loader.get_api_key(env)
    if not api_key:
        return None, (
            "Clé API Claude (Anthropic) non configurée. Renseignez "
            "ANTHROPIC_API_KEY dans /etc/odoo-server.conf ou le paramètre "
            "« doorway_site_builder.anthropic_api_key »."
        )

    payload = {
        "model": get_model(env),
        "max_tokens": 8000,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": _build_user_prompt(brief, previous_plan, instruction),
            }
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        resp = requests.post(
            ANTHROPIC_URL, headers=headers, data=json.dumps(payload), timeout=120
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Site builder — réseau Claude : %s", exc)
        return None, "Service Claude injoignable. Réessayez plus tard."

    if resp.status_code != 200:
        _logger.warning(
            "Site builder — Claude HTTP %s : %s", resp.status_code, resp.text[:300]
        )
        return None, (
            "Claude a renvoyé une erreur (HTTP %s). Vérifiez la clé API ou le "
            "modèle configuré." % resp.status_code
        )

    try:
        parts = resp.json().get("content") or []
        raw = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    except Exception:  # noqa: BLE001
        return None, "Réponse Claude illisible."

    plan = _parse_json(raw)
    if plan is None:
        return None, "Claude n'a pas renvoyé de plan JSON exploitable."
    return validate_plan(plan)
