# -*- coding: utf-8 -*-
import os


def _load_from_odoo_conf():
    """Lit les clés VICIDIAL_* depuis /etc/odoo-server.conf si présentes."""
    values = {}
    conf_path = "/etc/odoo-server.conf"
    try:
        with open(conf_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.startswith("VICIDIAL_") or key in (
                    "ELEVENLABS_API_KEY",
                    "TWILIO_ACCOUNT_SID",
                    "TWILIO_AUTH_TOKEN",
                    "TWILIO_PHONE_NUMBER",
                    "ANTHROPIC_API_KEY",
                ):
                    values[key] = val.strip()
    except OSError:
        pass
    return values


def post_init_hook(env):
    """Charge les variables VICIDIAL / API depuis l'environnement Odoo au premier install."""
    icp = env["ir.config_parameter"].sudo()
    conf_vals = _load_from_odoo_conf()
    mapping = {
        "doorway_agents_ia.elevenlabs_api_key": "ELEVENLABS_API_KEY",
        "doorway_agents_ia.twilio_account_sid": "TWILIO_ACCOUNT_SID",
        "doorway_agents_ia.twilio_auth_token": "TWILIO_AUTH_TOKEN",
        "doorway_agents_ia.twilio_phone_number": "TWILIO_PHONE_NUMBER",
        "doorway_agents_ia.anthropic_api_key": "ANTHROPIC_API_KEY",
        "doorway_agents_ia.vicidial_db_host": "VICIDIAL_DB_HOST",
        "doorway_agents_ia.vicidial_db_port": "VICIDIAL_DB_PORT",
        "doorway_agents_ia.vicidial_db_user": "VICIDIAL_DB_USER",
        "doorway_agents_ia.vicidial_db_password": "VICIDIAL_DB_PASSWORD",
        "doorway_agents_ia.vicidial_db_name": "VICIDIAL_DB_NAME",
    }
    conf_to_param = {
        "VICIDIAL_DB_HOST": "doorway_agents_ia.vicidial_db_host",
        "VICIDIAL_DB_PORT": "doorway_agents_ia.vicidial_db_port",
        "VICIDIAL_DB_USER": "doorway_agents_ia.vicidial_db_user",
        "VICIDIAL_DB_PASSWORD": "doorway_agents_ia.vicidial_db_password",
        "VICIDIAL_DB_NAME": "doorway_agents_ia.vicidial_db_name",
        "ELEVENLABS_API_KEY": "doorway_agents_ia.elevenlabs_api_key",
        "TWILIO_ACCOUNT_SID": "doorway_agents_ia.twilio_account_sid",
        "TWILIO_AUTH_TOKEN": "doorway_agents_ia.twilio_auth_token",
        "TWILIO_PHONE_NUMBER": "doorway_agents_ia.twilio_phone_number",
        "ANTHROPIC_API_KEY": "doorway_agents_ia.anthropic_api_key",
    }
    for conf_key, param_key in conf_to_param.items():
        if not icp.get_param(param_key) and conf_vals.get(conf_key):
            icp.set_param(param_key, conf_vals[conf_key])
    for param_key, env_key in mapping.items():
        if not icp.get_param(param_key):
            val = os.environ.get(env_key) or conf_vals.get(env_key)
            if val:
                icp.set_param(param_key, val)
