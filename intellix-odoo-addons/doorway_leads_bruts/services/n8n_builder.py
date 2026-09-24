# -*- coding: utf-8 -*-
"""Constructeur de workflow n8n pour le Configurateur INTLX-EXT.

Port Python du fichier de référence ``n8n-builder.js`` (brief).
Génère le JSON d'un workflow n8n complet à partir des paramètres de campagne,
puis le crée via l'API REST n8n (``POST /api/v1/workflows``), en mode INACTIF.

ÉCHEC PROPRE : si la clé X-N8N-API-KEY est absente, ``build_and_deploy`` renvoie
``{"success": False, "error": "..."}`` sans lever d'exception.

⚠️ POINT D'EXTENSION BRIGHT DATA (2e passe) : voir ``_build_extraction_node``.
"""
import json
import logging
import time
from urllib.parse import quote

import requests

_logger = logging.getLogger(__name__)

# --- Paramètres de configuration (ir.config_parameter) ---
N8N_URL_PARAM = "doorway_leads_bruts.n8n_url"
N8N_API_KEY_PARAM = "doorway_leads_bruts.n8n_api_key"
ODOO_URL_PARAM = "doorway_leads_bruts.odoo_base_url"
CRM_TAG_PARAM = "doorway_leads_bruts.crm_tag_id"
CRM_TEAM_PARAM = "doorway_leads_bruts.crm_team_id"

DEFAULT_N8N_URL = "http://127.0.0.1:5678"


# ----------------------------------------------------------------------
# Helpers de configuration
# ----------------------------------------------------------------------
def get_n8n_base_url(env):
    icp = env["ir.config_parameter"].sudo()
    return (icp.get_param(N8N_URL_PARAM) or DEFAULT_N8N_URL).rstrip("/")


def get_n8n_api_key(env):
    return (env["ir.config_parameter"].sudo().get_param(N8N_API_KEY_PARAM) or "").strip()


def get_odoo_base_url(env):
    icp = env["ir.config_parameter"].sudo()
    return (
        icp.get_param(ODOO_URL_PARAM) or icp.get_param("web.base.url") or ""
    ).rstrip("/")


def is_available(env):
    return bool(get_n8n_api_key(env))


# ----------------------------------------------------------------------
# Construction des URLs de scraping
# ----------------------------------------------------------------------
def build_source_url(source, campagne):
    """url_pattern.replace {secteur},{zone} (encodeURIComponent)."""
    pattern = source.get("url_pattern") or ""
    if not pattern:
        return ""
    secteur = quote(str(campagne.get("secteur") or ""))
    zone = quote(str(campagne.get("zone") or ""))
    return pattern.replace("{secteur}", secteur).replace("{zone}", zone)


# ----------------------------------------------------------------------
# Construction des nœuds n8n
# ----------------------------------------------------------------------
def _build_extraction_node(source, campagne, position):
    """Construit le nœud d'extraction pour UNE source.

    =====================================================================
    ⚠️  SEAM BRIGHT DATA — 2e PASSE
    ---------------------------------------------------------------------
    Aujourd'hui (MVP) ce nœud est un simple ``httpRequest`` GET naïf vers
    l'``url_pattern`` de la source (comportement de référence du brief).

    En 2e passe, remplacer le corps de cette fonction par la construction
    d'un nœud appelant Bright Data (Web Unlocker / SERP / Dataset API),
    p.ex. via les credentials Bright Data stockés dans n8n, SANS toucher
    au reste du graphe (connexions identiques). C'est le SEUL endroit à
    modifier pour brancher un vrai provider de scraping.

    TODO(BrightData): if source.get("provider") == "brightdata": ...
    =====================================================================
    """
    url = build_source_url(source, campagne)
    return {
        "id": "scrape_%s" % source.get("id"),
        "name": "Scraping — %s" % source.get("label"),
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "parameters": {
            "url": url or "https://example.invalid/{zone}".replace(
                "{zone}", quote(str(campagne.get("zone") or ""))
            ),
            "method": "GET",
            "options": {
                "response": {"response": {"responseFormat": "text"}},
                "timeout": 30000,
            },
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {
                        "name": "User-Agent",
                        "value": "Mozilla/5.0 (compatible; IntelliXBot/1.0)",
                    },
                    {"name": "Accept-Language", "value": "fr"},
                ]
            },
            # Métadonnée du seam pour la 2e passe (lecture côté n8n / debug).
            "_intlx_source_id": source.get("id"),
            "_intlx_extraction_provider": "httpRequest",
        },
    }


def _build_scoring_prompt(campagne, advice):
    criteres = (advice or {}).get("filtres_critiques") or []
    return (
        "Tu es un expert en qualification de leads pour le secteur "
        f"{campagne.get('secteur')} en {campagne.get('pays')}. "
        "Évalue le lead et réponds UNIQUEMENT en JSON : "
        '{"score_ia": 0-100, "score_resume": "...", "segment": "...", '
        '"signal_detecte": "...", "priorite": "haute|moyenne|basse"}. '
        "Critères de qualité : " + ", ".join(criteres)
    )


def build_nodes(campagne, sources, advice):
    nodes = []

    nodes.append({
        "id": "schedule_trigger",
        "name": "Déclencheur planifié",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.1,
        "position": [240, 300],
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "hours",
                        "hoursInterval": int(campagne.get("frequence_heures") or 24),
                    }
                ]
            }
        },
    })

    nodes.append({
        "id": "config_campagne",
        "name": "Config Campagne",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3,
        "position": [460, 300],
        "parameters": {
            "assignments": {
                "assignments": [
                    {"id": "a1", "name": "campagne_id", "type": "string",
                     "value": str(campagne.get("campagne_id") or "")},
                    {"id": "a2", "name": "pays", "type": "string",
                     "value": campagne.get("pays") or ""},
                    {"id": "a3", "name": "secteur", "type": "string",
                     "value": campagne.get("secteur") or ""},
                    {"id": "a4", "name": "zone", "type": "string",
                     "value": campagne.get("zone") or ""},
                    {"id": "a5", "name": "cible", "type": "string",
                     "value": campagne.get("cible") or ""},
                    {"id": "a6", "name": "objectif_leads", "type": "number",
                     "value": int(campagne.get("objectif_leads") or 0)},
                    {"id": "a7", "name": "mots_cles", "type": "string",
                     "value": json.dumps((advice or {}).get("mots_cles_recherche") or [],
                                         ensure_ascii=False)},
                    {"id": "a8", "name": "filtres", "type": "string",
                     "value": json.dumps((advice or {}).get("filtres_critiques") or [],
                                         ensure_ascii=False)},
                ]
            }
        },
    })

    x = 680
    for source in sources:
        nodes.append(_build_extraction_node(source, campagne, [x, 200]))
        x += 220

    nodes.append({
        "id": "fusion_sources",
        "name": "Fusion Sources",
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [x + 40, 300],
        "parameters": {"mode": "combine", "combineBy": "combineByPosition"},
    })

    nodes.append({
        "id": "claude_scoring",
        "name": "Claude Scoring",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x + 260, 300],
        "parameters": {
            "url": "https://api.anthropic.com/v1/messages",
            "method": "POST",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "x-api-key", "value": "={{$env.CLAUDE_KEY}}"},
                    {"name": "anthropic-version", "value": "2023-06-01"},
                    {"name": "content-type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "system": _build_scoring_prompt(campagne, advice),
                "messages": [
                    {"role": "user", "content": "={{JSON.stringify($json)}}"}
                ],
            }, ensure_ascii=False),
        },
    })

    is_france = (campagne.get("pays") == "france")
    if is_france:
        nodes.append({
            "id": "verif_bloctel",
            "name": "Vérif Bloctel (DNC France)",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [x + 480, 300],
            "parameters": {
                "url": "={{$env.VPS_URL}}/api/dnc/check-bloctel",
                "method": "POST",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={{ { "telephone": $json.telephone } }}',
                # TODO(DNC/Bloctel — 2e passe) : brancher un vrai vérificateur
                # Bloctel/CRTC DNCL. Placeholder pour l'instant.
                "_intlx_placeholder": True,
            },
        })

    nodes.append({
        "id": "filtre_qualite",
        "name": "Filtre Qualité",
        "type": "n8n-nodes-base.filter",
        "typeVersion": 2,
        "position": [x + 700, 300],
        "parameters": {
            "conditions": {
                "combinator": "and",
                "conditions": [
                    {
                        "leftValue": "={{$json.score_ia}}",
                        "rightValue": 60,
                        "operator": {"type": "number", "operation": "gte"},
                    },
                    {
                        "leftValue": "={{$json.dnc_bloque}}",
                        "rightValue": False,
                        "operator": {"type": "boolean", "operation": "false"},
                    },
                ],
            }
        },
    })

    odoo_url = campagne.get("odoo_url") or ""
    crm_tag = campagne.get("crm_tag_id") or 0
    crm_team = campagne.get("crm_team_id") or 0
    nodes.append({
        "id": "odoo_creer_lead",
        "name": "Odoo — Créer Lead",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x + 920, 300],
        "parameters": {
            "url": "%s/web/dataset/call_kw" % (odoo_url or "={{$env.ODOO_URL}}"),
            "method": "POST",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": "crm.lead",
                    "method": "create",
                    "args": [{
                        "name": "={{$json.name}}",
                        "phone": "={{$json.phone}}",
                        "email_from": "={{$json.email}}",
                        "description": "={{$json.score_resume}}",
                        "tag_ids": [[6, 0, [crm_tag] if crm_tag else []]],
                        "team_id": crm_team or False,
                    }],
                    "kwargs": {},
                },
            }, ensure_ascii=False),
        },
    })

    nodes.append({
        "id": "rapport_whatsapp",
        "name": "Rapport WhatsApp Superviseur",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x + 1140, 300],
        "parameters": {
            "url": "={{$env.VPS_URL}}/api/whatsapp/send",
            "method": "POST",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": (
                '={{ { "to": $env.SUPERVISEUR_WHATSAPP, "message": '
                '"[INTELLIX] Campagne ' + (campagne.get("nom_campagne") or "")
                + ' — nouveau lead qualifié: " + $json.name } }}'
            ),
            # TODO(WhatsApp — 2e passe) : aucun message réel n'est envoyé tant
            # que le workflow reste INACTIF.
            "_intlx_placeholder": True,
        },
    })

    return nodes


def _conn(target):
    return {"node": target, "type": "main", "index": 0}


def build_connections(campagne, sources):
    connections = {}

    connections["Déclencheur planifié"] = {"main": [[_conn("Config Campagne")]]}

    scrape_names = ["Scraping — %s" % s.get("label") for s in sources]
    if scrape_names:
        connections["Config Campagne"] = {
            "main": [[_conn(n) for n in scrape_names]]
        }
        for name in scrape_names:
            connections[name] = {"main": [[_conn("Fusion Sources")]]}
    else:
        connections["Config Campagne"] = {"main": [[_conn("Fusion Sources")]]}

    connections["Fusion Sources"] = {"main": [[_conn("Claude Scoring")]]}

    if campagne.get("pays") == "france":
        connections["Claude Scoring"] = {
            "main": [[_conn("Vérif Bloctel (DNC France)")]]
        }
        connections["Vérif Bloctel (DNC France)"] = {
            "main": [[_conn("Filtre Qualité")]]
        }
    else:
        connections["Claude Scoring"] = {"main": [[_conn("Filtre Qualité")]]}

    connections["Filtre Qualité"] = {"main": [[_conn("Odoo — Créer Lead")]]}
    connections["Odoo — Créer Lead"] = {
        "main": [[_conn("Rapport WhatsApp Superviseur")]]
    }
    return connections


def build_workflow_payload(campagne, sources, advice):
    """Construit le payload complet du workflow n8n (sans le déployer)."""
    nodes = build_nodes(campagne, sources, advice)
    connections = build_connections(campagne, sources)
    return {
        "name": "[INTELLIX] %s — %s" % (
            campagne.get("nom_campagne") or "Campagne",
            campagne.get("zone") or "",
        ),
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner",
        },
    }


def build_and_deploy(env, campagne, sources, advice):
    """Construit puis crée le workflow dans n8n (active=False).

    Renvoie un dict ``{success, workflow_id, workflow_name, n8n_url, error}``.
    Ne lève jamais : échoue proprement si la clé API n'est pas configurée.
    """
    api_key = get_n8n_api_key(env)
    base_url = get_n8n_base_url(env)
    workflow_name = "[INTELLIX] %s — %s" % (
        campagne.get("nom_campagne") or "Campagne",
        campagne.get("zone") or "",
    )

    if not api_key:
        return {
            "success": False,
            "workflow_name": workflow_name,
            "error": (
                "Clé API n8n non configurée. Renseignez "
                "« doorway_leads_bruts.n8n_api_key » (n8n → Settings → API → "
                "Create an API key) pour permettre le déploiement."
            ),
        }

    payload = build_workflow_payload(campagne, sources, advice)
    try:
        resp = requests.post(
            "%s/api/v1/workflows" % base_url,
            headers={
                "X-N8N-API-KEY": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=json.dumps(payload),
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("n8n deploy — réseau : %s", exc)
        return {
            "success": False,
            "workflow_name": workflow_name,
            "error": "Service n8n injoignable (%s)." % base_url,
        }

    if resp.status_code not in (200, 201):
        _logger.warning("n8n deploy HTTP %s : %s", resp.status_code, resp.text[:300])
        return {
            "success": False,
            "workflow_name": workflow_name,
            "error": "n8n a renvoyé une erreur (HTTP %s)." % resp.status_code,
        }

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {}
    workflow_id = data.get("id") or ""
    return {
        "success": True,
        "workflow_id": workflow_id,
        "workflow_name": data.get("name") or workflow_name,
        "n8n_url": "%s/workflow/%s" % (base_url, workflow_id) if workflow_id else base_url,
        "active": False,
    }


def make_local_workflow_id():
    """Identifiant local INTLX-EXT-<ts> (référence brief)."""
    return "INTLX-EXT-%d" % int(time.time() * 1000)
