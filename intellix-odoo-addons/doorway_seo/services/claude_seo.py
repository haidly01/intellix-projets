# -*- coding: utf-8 -*-
"""Service Claude (Anthropic) pour le module SEO IA.

Trois familles d'appels, toutes conçues pour ÉCHOUER PROPREMENT (clé absente,
réseau, HTTP, JSON invalide → ``(None, message)`` sans jamais lever) :

  - ``generate_page_seo`` : meta title/description, mots-clés, JSON-LD et pistes
    d'amélioration pour une page donnée (à partir de son audit).
  - ``generate_backlink_targets`` : cibles de backlinks WHITE-HAT à partir d'un
    brief (+ éventuels résultats SERP Bright Data en contexte).
  - ``generate_outreach_email`` : email d'approche (sujet + corps) pour une cible.
  - ``generate_citation_content`` : contenu de soumission pour un annuaire donné.
"""
import json
import logging

import requests

from . import config_loader

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

NO_KEY_MESSAGE = (
    "Clé API Claude (Anthropic) non configurée. Renseignez ANTHROPIC_API_KEY "
    "dans /etc/odoo-server.conf ou le paramètre « doorway_seo.anthropic_api_key »."
)

SYSTEM_SEO = (
    "Tu es un expert SEO senior, white-hat strict (jamais de techniques "
    "pénalisées par Google : pas de bourrage de mots-clés, pas de cloaking, "
    "pas de PBN, pas de spam). Tu réponds UNIQUEMENT avec un objet JSON valide, "
    "sans aucun texte autour, sans préambule, sans backticks."
)


def is_available(env):
    return config_loader.is_available(env)


# ----------------------------------------------------------------------------
# Bas niveau : appel HTTP + parsing JSON robuste
# ----------------------------------------------------------------------------
def _call(env, user_prompt, max_tokens=3000, system=SYSTEM_SEO):
    api_key = config_loader.get_api_key(env)
    if not api_key:
        return None, NO_KEY_MESSAGE
    payload = {
        "model": config_loader.get_model(env),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_prompt}],
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
        _logger.warning("SEO IA — réseau Claude : %s", exc)
        return None, "Service Claude injoignable. Réessayez plus tard."
    if resp.status_code != 200:
        _logger.warning("SEO IA — Claude HTTP %s : %s", resp.status_code, resp.text[:300])
        return None, (
            "Claude a renvoyé une erreur (HTTP %s). Vérifiez la clé API ou le "
            "modèle configuré." % resp.status_code
        )
    try:
        parts = resp.json().get("content") or []
        raw = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    except Exception:  # noqa: BLE001
        return None, "Réponse Claude illisible."
    data = _parse_json(raw)
    if data is None:
        return None, "Claude n'a pas renvoyé de JSON exploitable."
    return data, "OK"


def _parse_json(raw):
    """Strip fences ```json puis json.loads sur le premier objet/array {...}/[...]"""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    # On respecte le délimiteur de plus haut niveau (objet vs tableau) : on
    # essaie d'abord celui qui apparaît en premier dans le texte.
    obj_pos = text.find("{")
    arr_pos = text.find("[")
    if arr_pos != -1 and (obj_pos == -1 or arr_pos < obj_pos):
        order = (("[", "]"), ("{", "}"))
    else:
        order = (("{", "}"), ("[", "]"))
    for opener, closer in order:
        start = text.find(opener)
        end = text.rfind(closer) + 1
        if 0 <= start < end:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    _logger.warning("SEO IA : JSON Claude invalide")
    return None


def _as_list(value):
    if isinstance(value, list):
        return [v for v in value if v not in (None, "")]
    if value in (None, ""):
        return []
    return [value]


def _str(value, limit=None):
    s = (value if isinstance(value, str) else ("" if value is None else str(value))).strip()
    return s[:limit] if limit else s


# ----------------------------------------------------------------------------
# 0) Idéation de mots-clés (recherche de mots-clés)
# ----------------------------------------------------------------------------
def generate_keyword_ideas(env, seed, geo="", language="fr", serp_context=None, count=20):
    """Renvoie (list|None, message) d'idées de mots-clés.

    Chaque idée : {keyword, intent (informational/commercial/transactional/
    navigational/local), rationale, group}. ``serp_context`` (recherches
    associées / PAA / autocomplete Bright Data) est fourni en contexte mais
    n'est jamais requis.
    """
    schema = [
        {
            "keyword": "expression de mot-clé",
            "intent": "informational|commercial|transactional|navigational|local",
            "group": "thème / regroupement court",
            "rationale": "pourquoi c'est pertinent (1 phrase)",
        }
    ]
    parts = [
        "Génère une liste d'IDÉES DE MOTS-CLÉS SEO pertinentes et réalistes "
        "autour de ce sujet, pour le référencement naturel.",
        "",
        "LANGUE DE SORTIE : %s" % (language or "fr"),
        "SUJET / MOT-CLÉ AMORCE : %s" % (seed or ""),
        "ZONE GÉOGRAPHIQUE : %s" % (geo or "(non précisé)"),
        "",
    ]
    if serp_context:
        parts += [
            "SIGNAUX SERP RÉELS (recherches associées / PAA / autocomplétion — "
            "à exploiter et regrouper, sans tout recopier) :",
            json.dumps(serp_context, ensure_ascii=False)[:4000],
            "",
        ]
    parts += [
        "CONTRAINTES :",
        "- %d idées maximum, variées (longue traîne incluse), sans doublons." % int(count),
        "- Mélange d'intentions (info, commerciale, transactionnelle, locale).",
        "- Inclure des variantes locales si une zone géographique est fournie.",
        "- Mots-clés réalistes que de vraies personnes tapent ; pas de bourrage.",
        "- N'invente AUCUN chiffre de volume ni de difficulté (calculés ailleurs).",
        "",
        "Réponds STRICTEMENT avec un TABLEAU JSON d'objets respectant ce schéma :",
        json.dumps(schema, ensure_ascii=False),
    ]
    data, message = _call(env, "\n".join(parts), max_tokens=3000)
    if data is None:
        return None, message
    if isinstance(data, dict):
        data = data.get("keywords") or data.get("ideas") or []
    if not isinstance(data, list):
        return None, "Réponse mots-clés inattendue (tableau JSON attendu)."
    allowed_intents = {
        "informational", "commercial", "transactional", "navigational", "local",
    }
    out = []
    seen = set()
    for item in data[: int(count)]:
        if not isinstance(item, dict):
            continue
        kw = _str(item.get("keyword"), 160)
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        intent = _str(item.get("intent")).lower()
        if intent not in allowed_intents:
            intent = "informational"
        out.append(
            {
                "keyword": kw,
                "intent": intent,
                "group": _str(item.get("group"), 80),
                "rationale": _str(item.get("rationale"), 400),
            }
        )
    if not out:
        return None, "Aucune idée de mot-clé exploitable."
    return out, "%d idée(s) de mots-clés générée(s)." % len(out)


# ----------------------------------------------------------------------------
# 1) SEO on-page
# ----------------------------------------------------------------------------
def generate_page_seo(env, page_context, target_keyword="", language="fr"):
    """Renvoie (dict|None, message).

    dict = {meta_title, meta_description, keywords:[...], jsonld:{...},
            suggestions:[...]}
    """
    schema = {
        "meta_title": "titre SEO accrocheur <= 60 caractères",
        "meta_description": "meta description persuasive 120-155 caractères",
        "keywords": ["mot-clé 1", "mot-clé 2", "..."],
        "jsonld": {
            "@context": "https://schema.org",
            "@type": "WebPage|Organization|LocalBusiness|Service",
            "name": "...",
            "description": "...",
        },
        "suggestions": [
            "amélioration de contenu concrète 1",
            "amélioration de contenu concrète 2",
        ],
    }
    parts = [
        "Optimise le SEO ON-PAGE de cette page d'un site vitrine.",
        "",
        "LANGUE DE SORTIE : %s" % (language or "fr"),
        "MOT-CLÉ CIBLE : %s" % (target_keyword or "(non précisé — déduis-le du contenu)"),
        "",
        "DONNÉES DE LA PAGE (audit) :",
        json.dumps(page_context, ensure_ascii=False)[:6000],
        "",
        "CONTRAINTES :",
        "- meta_title <= 60 caractères, inclut naturellement le mot-clé si pertinent.",
        "- meta_description entre 120 et 155 caractères, incitative, sans bourrage.",
        "- keywords : 4 à 8 expressions pertinentes, pas de répétition abusive.",
        "- jsonld : un objet schema.org VALIDE et cohérent avec le type de page "
        "(WebPage, Organization, LocalBusiness ou Service). Pas de fausses infos.",
        "- suggestions : 3 à 6 actions concrètes (titres, contenu, maillage, alt).",
        "- WHITE-HAT strict : jamais de keyword stuffing ni de contenu trompeur.",
        "",
        "Réponds STRICTEMENT avec un objet JSON respectant ce schéma :",
        json.dumps(schema, ensure_ascii=False),
    ]
    data, message = _call(env, "\n".join(parts), max_tokens=2500)
    if data is None:
        return None, message
    if not isinstance(data, dict):
        return None, "Réponse SEO inattendue (objet JSON attendu)."
    jsonld = data.get("jsonld")
    if not isinstance(jsonld, dict):
        jsonld = {}
    clean = {
        "meta_title": _str(data.get("meta_title"), 70),
        "meta_description": _str(data.get("meta_description"), 200),
        "keywords": [_str(k, 60) for k in _as_list(data.get("keywords"))][:8],
        "jsonld": jsonld,
        "suggestions": [_str(s, 400) for s in _as_list(data.get("suggestions"))][:8],
    }
    if not clean["meta_title"] and not clean["meta_description"]:
        return None, "Claude n'a pas proposé de meta exploitables."
    return clean, "Proposition SEO générée."


# ----------------------------------------------------------------------------
# 2) Backlinks white-hat
# ----------------------------------------------------------------------------
ALLOWED_BACKLINK_TYPES = [
    "blog_sectoriel", "partenaire", "presse_locale", "page_ressource",
    "annuaire", "association", "evenement", "institution", "autre",
]


def generate_backlink_targets(env, brief, serp_context=None, count=8):
    """Renvoie (list|None, message) de cibles de backlinks WHITE-HAT."""
    schema = [
        {
            "name": "nom du site / média / partenaire",
            "type": "|".join(ALLOWED_BACKLINK_TYPES),
            "url": "https://exemple.com (ou domaine probable, jamais inventé de page exacte)",
            "approach": "comment obtenir un lien de façon légitime (contenu invité, "
            "partenariat, mention, ressource utile, communiqué…)",
            "rationale": "pourquoi c'est pertinent + estimation d'autorité/notoriété",
        }
    ]
    parts = [
        "Propose une liste de CIBLES DE BACKLINKS 100% WHITE-HAT pour ce client.",
        "",
        "BRIEF :",
        json.dumps(brief, ensure_ascii=False),
        "",
    ]
    if serp_context:
        parts += [
            "RÉSULTATS DE RECHERCHE (contexte, à filtrer/qualifier, ne pas tout reprendre) :",
            json.dumps(serp_context, ensure_ascii=False)[:4000],
            "",
        ]
    parts += [
        "RÈGLES STRICTES (TRÈS IMPORTANT) :",
        "- UNIQUEMENT des opportunités LÉGITIMES : blogs sectoriels, partenaires, "
        "presse/médias locaux, pages ressources, annuaires pertinents, associations, "
        "événements, institutions.",
        "- INTERDIT : fermes de liens, PBN, spam de commentaires/forums, achat de "
        "liens, échanges massifs, sites sans rapport. N'en propose JAMAIS.",
        "- Chaque cible doit être réaliste et atteignable par une démarche honnête.",
        "- N'invente pas d'URL de page exacte ; un domaine plausible suffit.",
        "- %d cibles maximum, triées par pertinence." % int(count),
        "",
        "Réponds STRICTEMENT avec un TABLEAU JSON d'objets respectant ce schéma :",
        json.dumps(schema, ensure_ascii=False),
    ]
    data, message = _call(env, "\n".join(parts), max_tokens=3500)
    if data is None:
        return None, message
    if isinstance(data, dict):
        data = data.get("targets") or data.get("backlinks") or []
    if not isinstance(data, list):
        return None, "Réponse backlinks inattendue (tableau JSON attendu)."
    out = []
    for item in data[: int(count)]:
        if not isinstance(item, dict):
            continue
        btype = _str(item.get("type")).lower().replace(" ", "_")
        if btype not in ALLOWED_BACKLINK_TYPES:
            btype = "autre"
        name = _str(item.get("name"), 200)
        if not name:
            continue
        out.append(
            {
                "name": name,
                "type": btype,
                "url": _str(item.get("url"), 300),
                "approach": _str(item.get("approach"), 1000),
                "rationale": _str(item.get("rationale"), 1000),
            }
        )
    if not out:
        return None, "Aucune cible exploitable proposée."
    return out, "%d cible(s) de backlinks proposée(s)." % len(out)


def generate_outreach_email(env, brief, target, language="fr"):
    """Renvoie (dict|None, message) : {subject, body}."""
    schema = {
        "subject": "objet d'email court et personnalisé",
        "body": "corps d'email professionnel, personnalisé, honnête, avec une "
        "proposition de valeur claire et un appel à l'action léger (texte brut, "
        "sauts de ligne autorisés)",
    }
    parts = [
        "Rédige un EMAIL D'APPROCHE (outreach) légitime pour obtenir un backlink "
        "ou un partenariat avec cette cible. Aucune manipulation, pas de promesse "
        "trompeuse, pas d'offre d'achat de lien.",
        "",
        "LANGUE : %s" % (language or "fr"),
        "EXPÉDITEUR / CLIENT :",
        json.dumps(brief, ensure_ascii=False),
        "",
        "CIBLE :",
        json.dumps(target, ensure_ascii=False),
        "",
        "CONTRAINTES : ton respectueux et concret, 120-200 mots, personnalisé selon "
        "la cible, propose une vraie valeur (contenu, collaboration, ressource). "
        "Termine par une signature générique [Votre nom / Entreprise].",
        "",
        "Réponds STRICTEMENT avec un objet JSON :",
        json.dumps(schema, ensure_ascii=False),
    ]
    data, message = _call(env, "\n".join(parts), max_tokens=1500)
    if data is None:
        return None, message
    if not isinstance(data, dict):
        return None, "Réponse outreach inattendue."
    clean = {
        "subject": _str(data.get("subject"), 300),
        "body": _str(data.get("body"), 6000),
    }
    if not clean["body"]:
        return None, "Email d'approche vide."
    return clean, "Email d'approche généré."


# ----------------------------------------------------------------------------
# 3) Citations / annuaires
# ----------------------------------------------------------------------------
def generate_citation_content(env, nap, directory, language="fr"):
    """Renvoie (dict|None, message) : contenu de soumission pour un annuaire."""
    schema = {
        "business_description": "description NAP-cohérente adaptée au format de "
        "l'annuaire (longueur selon 'format_hint')",
        "short_description": "version courte (<= 160 caractères)",
        "categories": ["catégorie 1", "catégorie 2"],
        "keywords": ["mot-clé local 1", "mot-clé local 2"],
        "tagline": "accroche courte (optionnel)",
        "notes": "conseils de soumission spécifiques à cet annuaire",
    }
    parts = [
        "Génère un CONTENU DE SOUMISSION prêt à coller pour inscrire cette "
        "entreprise dans l'annuaire ci-dessous (SEO local). Respecte une "
        "cohérence NAP stricte (mêmes nom/adresse/téléphone partout).",
        "",
        "LANGUE : %s" % (language or "fr"),
        "FICHE ENTREPRISE (NAP) :",
        json.dumps(nap, ensure_ascii=False),
        "",
        "ANNUAIRE CIBLE :",
        json.dumps(directory, ensure_ascii=False),
        "",
        "CONTRAINTES : descriptions naturelles et utiles, pas de bourrage de "
        "mots-clés, catégories réalistes pour cet annuaire, mots-clés à intention "
        "locale. Ne modifie jamais le NAP (nom/adresse/téléphone).",
        "",
        "Réponds STRICTEMENT avec un objet JSON :",
        json.dumps(schema, ensure_ascii=False),
    ]
    data, message = _call(env, "\n".join(parts), max_tokens=1800)
    if data is None:
        return None, message
    if not isinstance(data, dict):
        return None, "Réponse citation inattendue."
    clean = {
        "business_description": _str(data.get("business_description"), 4000),
        "short_description": _str(data.get("short_description"), 300),
        "categories": [_str(c, 80) for c in _as_list(data.get("categories"))][:8],
        "keywords": [_str(k, 60) for k in _as_list(data.get("keywords"))][:10],
        "tagline": _str(data.get("tagline"), 200),
        "notes": _str(data.get("notes"), 1000),
    }
    if not clean["business_description"]:
        return None, "Contenu de citation vide."
    return clean, "Contenu de citation généré."
