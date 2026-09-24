# -*- coding: utf-8 -*-
"""Conseiller Claude (Anthropic) pour le Configurateur de Campagnes INTLX-EXT.

Port Python du fichier de référence ``claude-advisor.js`` (brief).
Claude analyse la demande client et recommande sources + stratégie.

Tout est conçu pour ÉCHOUER PROPREMENT : si aucune clé API n'est configurée,
``advise_campaign`` renvoie ``(None, message)`` sans jamais lever d'exception.
"""
import json
import logging

import requests

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Clé principale du module + clés réutilisables déjà présentes dans la config
# d'autres modules Intellix (détection automatique demandée par le brief).
API_KEY_PARAM = "doorway_leads_bruts.claude_api_key"
FALLBACK_API_KEY_PARAMS = (
    "doorway_agents_ia.anthropic_api_key",
    "doorway_agents_dashboard.anthropic_api_key",
    "renovation_conciergerie.anthropic_api_key",
    "doorway_traffic_manager.anthropic_api_key",
    "doorway_social_ia.anthropic_api_key",
)

SYSTEM_PROMPT = (
    "Tu es un conseiller expert en extraction de données et génération de leads "
    "pour call centers. Réponds UNIQUEMENT en JSON valide, sans préambule ni "
    "backticks."
)


def get_api_key(env):
    """Renvoie la clé Anthropic à utiliser (clé module puis fallbacks)."""
    icp = env["ir.config_parameter"].sudo()
    key = icp.get_param(API_KEY_PARAM)
    if key:
        return key.strip()
    for param in FALLBACK_API_KEY_PARAMS:
        key = icp.get_param(param)
        if key:
            return key.strip()
    return ""


def is_available(env):
    return bool(get_api_key(env))


def _build_prompt(config, sources):
    """Construit le prompt utilisateur envoyé à Claude."""
    sources_min = [
        {
            "source_id": s.get("id"),
            "label": s.get("label"),
            "qualite": s.get("qualite"),
            "cout_estime": s.get("cout_estime"),
            "types_leads": s.get("types_leads"),
            "signal_intention": s.get("signal_intention"),
        }
        for s in (sources or [])
    ]
    demande = {
        "pays": config.get("pays"),
        "secteur": config.get("secteur"),
        "zone": config.get("zone"),
        "cible": config.get("cible"),
        "budget_mensuel": config.get("budget_mensuel"),
        "objectif_leads": config.get("objectif_leads"),
        "signal_intention": config.get("signal_intention"),
        "notes_client": config.get("notes_client"),
    }
    return (
        "Voici une demande de campagne d'extraction de leads :\n"
        f"{json.dumps(demande, ensure_ascii=False)}\n\n"
        "Sources disponibles pour ce pays/secteur :\n"
        f"{json.dumps(sources_min, ensure_ascii=False)}\n\n"
        "Analyse la demande et réponds STRICTEMENT avec ce JSON :\n"
        "{\n"
        '  "sources_recommandees": [{"source_id": "...", "priorite": 1, '
        '"raison": "...", "volume_estime": 100, "taux_conversion_estime": 0.05}],\n'
        '  "strategie_ciblage": "...",\n'
        '  "mots_cles_recherche": ["..."],\n'
        '  "filtres_critiques": ["..."],\n'
        '  "avertissements": ["..."],\n'
        '  "formule_recommandee": "INTLX-EXT-BRUT|INTLX-EXT-VER|INTLX-EXT-IA|INTLX-EXT-RDV",\n'
        '  "cout_estime_par_lead": 0.18,\n'
        '  "roi_estime": "..."\n'
        "}\n"
        "Les source_id recommandés DOIVENT provenir de la liste fournie."
    )


def _parse_json(raw):
    """Strip ```json fences puis json.loads. Renvoie None en cas d'échec."""
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
        _logger.warning("Claude advisor : JSON invalide")
        return None


def advise_campaign(env, config, sources=None):
    """Appelle Claude pour conseiller la campagne.

    Renvoie un tuple ``(advice_dict | None, message)``.
    Ne lève jamais : en cas de clé absente ou d'erreur réseau/API, renvoie
    ``(None, message_utilisateur)``.
    """
    api_key = get_api_key(env)
    if not api_key:
        return None, (
            "Clé API Claude (Anthropic) non configurée. "
            "Renseignez « doorway_leads_bruts.claude_api_key » dans les "
            "paramètres pour activer la recommandation IA."
        )

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_prompt(config, sources)}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        resp = requests.post(
            ANTHROPIC_URL, headers=headers, data=json.dumps(payload), timeout=60
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Claude advisor — réseau : %s", exc)
        return None, "Service Claude injoignable. Réessayez plus tard."

    if resp.status_code != 200:
        _logger.warning("Claude advisor HTTP %s : %s", resp.status_code, resp.text[:200])
        return None, (
            "Claude a renvoyé une erreur (HTTP %s). Vérifiez la clé API."
            % resp.status_code
        )

    try:
        parts = resp.json().get("content") or []
        raw = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    except Exception:  # noqa: BLE001
        return None, "Réponse Claude illisible."

    advice = _parse_json(raw)
    if advice is None:
        return None, "Claude n'a pas renvoyé de recommandation exploitable."
    return advice, "Recommandation IA générée."
