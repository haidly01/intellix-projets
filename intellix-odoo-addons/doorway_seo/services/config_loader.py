# -*- coding: utf-8 -*-
"""Résolution des clés / configuration pour le module SEO IA.

Anthropic (Claude) : variable d'env → /etc/odoo-server.conf → paramètres
``ir.config_parameter`` (clé du module puis fallbacks des autres modules
Intellix déjà configurés). Ne lève jamais.

Bright Data : TOTALEMENT OPTIONNEL. Sert uniquement à enrichir la découverte
SERP de backlinks et la vérification de citations. Si non configuré, les
fonctions renvoient ``{}`` / ``None`` et le module continue normalement.
"""
import os

CONF_PATH = "/etc/odoo-server.conf"

# ----------------------------------------------------------------------------
# Anthropic / Claude
# ----------------------------------------------------------------------------
ENV_KEY = "ANTHROPIC_API_KEY"
API_KEY_PARAM = "doorway_seo.anthropic_api_key"
FALLBACK_API_KEY_PARAMS = (
    "doorway_site_builder.anthropic_api_key",
    "doorway_email_builder.anthropic_api_key",
    "doorway_agents_dashboard.anthropic_api_key",
    "doorway_agents_ia.anthropic_api_key",
    "doorway_leads_bruts.claude_api_key",
    "renovation_conciergerie.anthropic_api_key",
    "doorway_traffic_manager.anthropic_api_key",
    "doorway_social_ia.anthropic_api_key",
)

MODEL_PARAM = "doorway_seo.claude_model"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ----------------------------------------------------------------------------
# Bright Data (optionnel)
# ----------------------------------------------------------------------------
BRIGHTDATA_ENV_KEY = "BRIGHTDATA_API_KEY"
BRIGHTDATA_KEY_PARAM = "doorway_seo.brightdata_api_key"
BRIGHTDATA_FALLBACK_KEY_PARAMS = (
    "doorway_leads_bruts.brightdata_api_key",
    "doorway_leads_bruts.bright_data_api_key",
    "doorway_agents_dashboard.brightdata_api_key",
)
BRIGHTDATA_ZONE_PARAM = "doorway_seo.brightdata_serp_zone"
BRIGHTDATA_FALLBACK_ZONE_PARAMS = (
    "doorway_leads_bruts.brightdata_serp_zone",
    "doorway_leads_bruts.brightdata_zone",
)

# ----------------------------------------------------------------------------
# Fournisseur de VOLUME de recherche (optionnel, PLUGGABLE)
# ----------------------------------------------------------------------------
# Permet de brancher plus tard une vraie API de volumes de mots-clés
# (ex: DataForSEO, Keyword Everywhere, etc.) sans toucher au code : on lit le
# provider + clé + endpoint depuis ir.config_parameter. Tant que rien n'est
# configuré, les volumes sont honnêtement marqués « estimé » / « N/A ».
KEYWORD_VOLUME_PROVIDER_PARAM = "doorway_seo.keyword_volume_provider"
KEYWORD_VOLUME_API_KEY_PARAM = "doorway_seo.keyword_volume_api_key"
KEYWORD_VOLUME_ENDPOINT_PARAM = "doorway_seo.keyword_volume_endpoint"
# Fournisseur par défaut si le paramètre n'est pas renseigné.
DEFAULT_KEYWORD_VOLUME_PROVIDER = "dataforseo"

# DataForSEO (fournisseur concret de volume + CPC + concurrence + difficulté).
# Auth HTTP Basic base64("<login>:<password>"). Compte pay-as-you-go.
DATAFORSEO_LOGIN_PARAM = "doorway_seo.dataforseo_login"
DATAFORSEO_PASSWORD_PARAM = "doorway_seo.dataforseo_password"
DATAFORSEO_MODE_PARAM = "doorway_seo.dataforseo_mode"  # 'live' (défaut) | 'task'
DATAFORSEO_LOCATION_PARAM = "doorway_seo.dataforseo_location"  # ex: "Canada" / "France"
DATAFORSEO_LANGUAGE_PARAM = "doorway_seo.dataforseo_language"  # ex: "French"


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


def _icp_first(env, params):
    if env is None:
        return ""
    icp = env["ir.config_parameter"].sudo()
    for param in params:
        value = icp.get_param(param)
        if value:
            return value.strip()
    return ""


# ----------------------------------------------------------------------------
# Public API — Anthropic
# ----------------------------------------------------------------------------
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
        return _icp_first(env, FALLBACK_API_KEY_PARAMS)
    return ""


def get_model(env):
    if env is None:
        return DEFAULT_MODEL
    icp = env["ir.config_parameter"].sudo()
    return (icp.get_param(MODEL_PARAM) or DEFAULT_MODEL).strip()


def is_available(env):
    return bool(get_api_key(env))


# ----------------------------------------------------------------------------
# Public API — Bright Data (optionnel)
# ----------------------------------------------------------------------------
def get_brightdata_config(env):
    """Renvoie {'api_key':..., 'zone':...} si configuré, sinon {}.

    Jamais requis : utilisé uniquement pour enrichir la découverte / vérifier.
    """
    api_key = (os.environ.get(BRIGHTDATA_ENV_KEY) or "").strip()
    if not api_key:
        api_key = _read_conf_value(BRIGHTDATA_ENV_KEY)
    if not api_key and env is not None:
        icp = env["ir.config_parameter"].sudo()
        api_key = (icp.get_param(BRIGHTDATA_KEY_PARAM) or "").strip()
        if not api_key:
            api_key = _icp_first(env, BRIGHTDATA_FALLBACK_KEY_PARAMS)
    if not api_key:
        return {}
    zone = ""
    if env is not None:
        icp = env["ir.config_parameter"].sudo()
        zone = (icp.get_param(BRIGHTDATA_ZONE_PARAM) or "").strip()
        if not zone:
            zone = _icp_first(env, BRIGHTDATA_FALLBACK_ZONE_PARAMS)
    return {"api_key": api_key, "zone": zone or "serp"}


def brightdata_available(env):
    return bool(get_brightdata_config(env))


# ----------------------------------------------------------------------------
# Public API — Volume de recherche (optionnel, pluggable)
# ----------------------------------------------------------------------------
def get_keyword_volume_config(env):
    """Renvoie {'provider':..., 'api_key':..., 'endpoint':...} ou {}.

    Le provider par défaut est ``dataforseo``. Mettre explicitement le paramètre
    ``doorway_seo.keyword_volume_provider`` à 'none'/'off' désactive tout
    fournisseur (volumes « estimé » / « N/A », jamais inventés).
    """
    if env is None:
        return {}
    icp = env["ir.config_parameter"].sudo()
    provider = (
        icp.get_param(KEYWORD_VOLUME_PROVIDER_PARAM) or DEFAULT_KEYWORD_VOLUME_PROVIDER
    ).strip().lower()
    if provider in ("none", "off", "disabled", "0", "false"):
        return {}
    return {
        "provider": provider,
        "api_key": (icp.get_param(KEYWORD_VOLUME_API_KEY_PARAM) or "").strip(),
        "endpoint": (icp.get_param(KEYWORD_VOLUME_ENDPOINT_PARAM) or "").strip(),
    }


def keyword_volume_available(env):
    """Vrai uniquement si le fournisseur sélectionné est RÉELLEMENT utilisable."""
    cfg = get_keyword_volume_config(env)
    if not cfg:
        return False
    provider = cfg.get("provider")
    if provider == "dataforseo":
        return dataforseo_available(env)
    if provider == "http":
        return bool(cfg.get("endpoint"))
    return False


def get_volume_provider_name(env):
    """Nom du fournisseur de volume sélectionné (pour l'UI)."""
    if env is None:
        return DEFAULT_KEYWORD_VOLUME_PROVIDER
    icp = env["ir.config_parameter"].sudo()
    return (
        icp.get_param(KEYWORD_VOLUME_PROVIDER_PARAM) or DEFAULT_KEYWORD_VOLUME_PROVIDER
    ).strip().lower()


# ----------------------------------------------------------------------------
# Public API — DataForSEO
# ----------------------------------------------------------------------------
def get_dataforseo_config(env):
    """Renvoie {'login','password','mode','location','language'} ou {} si non configuré."""
    login = (os.environ.get("DATAFORSEO_LOGIN") or "").strip()
    password = (os.environ.get("DATAFORSEO_PASSWORD") or "").strip()
    mode = "live"
    location = ""
    language = ""
    if env is not None:
        icp = env["ir.config_parameter"].sudo()
        login = login or (icp.get_param(DATAFORSEO_LOGIN_PARAM) or "").strip()
        password = password or (icp.get_param(DATAFORSEO_PASSWORD_PARAM) or "").strip()
        mode = (icp.get_param(DATAFORSEO_MODE_PARAM) or "live").strip().lower() or "live"
        location = (icp.get_param(DATAFORSEO_LOCATION_PARAM) or "").strip()
        language = (icp.get_param(DATAFORSEO_LANGUAGE_PARAM) or "").strip()
    if not login or not password:
        return {}
    return {
        "login": login,
        "password": password,
        "mode": mode if mode in ("live", "task") else "live",
        "location": location,
        "language": language,
    }


def dataforseo_available(env):
    return bool(get_dataforseo_config(env))
