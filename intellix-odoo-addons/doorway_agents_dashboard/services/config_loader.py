# -*- coding: utf-8 -*-
"""Lecture centralisée des clés API (env + odoo-server.conf + ir.config_parameter)."""
import os

CONF_PATH = "/etc/odoo-server.conf"

ENV_KEYS = (
    "ELEVENLABS_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
    "N8N_BASE_URL",
    "N8N_API_TOKEN",
    "N8N_AGENT_SYNC_PATH",
    "N8N_START_CALL_PATH",
    "N8N_START_WEB_TEST_PATH",
    "N8N_GET_CALL_PATH",
    "ANTHROPIC_API_KEY",
    "DOORWAY_AGENTS_WEBHOOK_KEY",
    "WHATSAPP_PHONE_ID",
    "WHATSAPP_TOKEN",
    "WHATSAPP_SENDER_E164",
)


def load_conf_values():
    values = {}
    try:
        with open(CONF_PATH, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line[0] in "#;":
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                if key in ENV_KEYS:
                    values[key] = val.strip()
    except OSError:
        pass
    return values


def get_secret(env, env_key, icp_key, fallback_icp_keys=None):
    """Priorité: env → odoo-server.conf → icp module → fallbacks icp."""
    value = os.environ.get(env_key, "")
    if not value:
        value = load_conf_values().get(env_key, "")
    if not value and env:
        icp = env["ir.config_parameter"].sudo()
        value = icp.get_param(icp_key) or ""
        for fb in fallback_icp_keys or ():
            if value:
                break
            value = icp.get_param(fb) or ""
    return (value or "").strip()
