# -*- coding: utf-8 -*-
"""Lecture de la clé API Anthropic (Claude) pour le Site Builder.

Priorité de résolution : variable d'env → /etc/odoo-server.conf → paramètres
``ir.config_parameter`` (clé du module puis fallbacks des autres modules
Intellix déjà configurés). Ne lève jamais.
"""
import os

CONF_PATH = "/etc/odoo-server.conf"
ENV_KEY = "ANTHROPIC_API_KEY"

# Clé propre au module (peut être renseignée dans les Paramètres) + fallbacks
# vers les clés déjà présentes dans la config des autres modules Intellix.
API_KEY_PARAM = "doorway_site_builder.anthropic_api_key"
FALLBACK_API_KEY_PARAMS = (
    "doorway_agents_dashboard.anthropic_api_key",
    "doorway_agents_ia.anthropic_api_key",
    "doorway_leads_bruts.claude_api_key",
    "renovation_conciergerie.anthropic_api_key",
    "doorway_traffic_manager.anthropic_api_key",
    "doorway_social_ia.anthropic_api_key",
)


def _read_conf_value(key):
    """Renvoie la valeur ``key`` lue dans odoo-server.conf, ou '' si absente."""
    try:
        with open(CONF_PATH, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line[0] in "#;" or "=" not in line:
                    continue
                conf_key, conf_val = line.split("=", 1)
                if conf_key.strip() == key:
                    return conf_val.strip()
    except OSError:
        pass
    return ""


def get_api_key(env):
    """Renvoie la clé Anthropic à utiliser (env → conf → ICP), ou ''."""
    value = (os.environ.get(ENV_KEY) or "").strip()
    if value:
        return value
    value = _read_conf_value(ENV_KEY)
    if value:
        return value
    if env is not None:
        icp = env["ir.config_parameter"].sudo()
        value = icp.get_param(API_KEY_PARAM)
        if value:
            return value.strip()
        for param in FALLBACK_API_KEY_PARAMS:
            value = icp.get_param(param)
            if value:
                return value.strip()
    return ""


def is_available(env):
    return bool(get_api_key(env))
