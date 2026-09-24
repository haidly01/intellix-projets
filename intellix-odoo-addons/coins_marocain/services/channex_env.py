# -*- coding: utf-8 -*-
"""Résolution d'environnement Channex — sans secret, sans dépendance Odoo.

Production (défaut) : https://app.channex.io/api/v1
Staging (repli)     : https://staging.channex.io/api/v1

La clé API se lit uniquement depuis CHANNEX_API_KEY (jamais en dur).
L'URL ICP staging est conservée pour un retour arrière.
"""
import os

PROD_URL = "https://app.channex.io/api/v1"
STAGING_URL = "https://staging.channex.io/api/v1"
DEFAULT_URL = PROD_URL

ENV_KEY = "CHANNEX_API_KEY"
ENV_URL = "CHANNEX_BASE_URL"
ENV_NAME = "CHANNEX_ENVIRONMENT"

PARAM_KEY = "coins.channex.api_key"
PARAM_URL = "coins.channex.base_url"
PARAM_ENABLED = "coins.channex.enabled"
PARAM_STAGING_URL = "coins.channex.staging_url"
PARAM_ENV = "coins.channex.environment"

ENVIRONMENT_PRODUCTION = "production"
ENVIRONMENT_STAGING = "staging"


def normalize_base_url(url):
    return (url or "").strip().rstrip("/")


def is_staging_url(url):
    return "staging.channex.io" in normalize_base_url(url).lower()


def is_production_url(url):
    host = normalize_base_url(url).lower()
    return "app.channex.io" in host or "api.channex.io" in host


def resolve_environment(explicit=None, icp_environment=None, icp_url=None, environ=None):
    env = environ if environ is not None else os.environ
    raw = (
        (explicit or "").strip()
        or (env.get(ENV_NAME) or "").strip()
        or (icp_environment or "").strip()
    ).lower()
    if raw in (ENVIRONMENT_STAGING, ENVIRONMENT_PRODUCTION):
        return raw
    if is_staging_url(icp_url) and not is_production_url(icp_url):
        return ENVIRONMENT_STAGING
    return ENVIRONMENT_PRODUCTION


def resolve_api_key(icp_value="", environ=None):
    """Env d'abord, ICP seulement en secours (ne jamais logger la valeur)."""
    env = environ if environ is not None else os.environ
    return (env.get(ENV_KEY) or icp_value or "").strip()


def resolve_base_url(
    icp_url="",
    environment=None,
    staging_url=None,
    environ=None,
):
    """CHANNEX_BASE_URL > ICP > URL de l'environnement choisi."""
    env = environ if environ is not None else os.environ
    override = normalize_base_url(env.get(ENV_URL) or "")
    if override:
        return override
    icp = normalize_base_url(icp_url)
    chosen = resolve_environment(
        environment, icp_environment=environment, icp_url=icp, environ=env
    )
    if chosen == ENVIRONMENT_STAGING:
        return normalize_base_url(staging_url) or STAGING_URL
    if icp and is_production_url(icp):
        return icp
    if icp and not is_staging_url(icp):
        return icp
    return PROD_URL


def rollback_url(staging_url=None):
    return normalize_base_url(staging_url) or STAGING_URL
