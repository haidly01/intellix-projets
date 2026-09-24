# -*- coding: utf-8 -*-
import logging
import os
import secrets

from odoo.tools import sql

from odoo.addons.doorway_agents_dashboard.services.config_loader import load_conf_values

_logger = logging.getLogger(__name__)

ENV_TO_ICP = {
    "ELEVENLABS_API_KEY": "doorway_agents_dashboard.elevenlabs_api_key",
    "TWILIO_ACCOUNT_SID": "doorway_agents_dashboard.twilio_account_sid",
    "TWILIO_AUTH_TOKEN": "doorway_agents_dashboard.twilio_auth_token",
    "TWILIO_FROM_NUMBER": "doorway_agents_dashboard.elevenlabs_from_number",
    "TWILIO_PHONE_NUMBER": "doorway_agents_dashboard.twilio_phone_number",
    "N8N_BASE_URL": "doorway_agents_dashboard.n8n_base_url",
    "N8N_API_TOKEN": "doorway_agents_dashboard.n8n_api_token",
    "N8N_AGENT_SYNC_PATH": "doorway_agents_dashboard.n8n_agent_sync_path",
    "N8N_START_CALL_PATH": "doorway_agents_dashboard.n8n_start_call_path",
    "N8N_GET_CALL_PATH": "doorway_agents_dashboard.n8n_get_call_path",
    "ANTHROPIC_API_KEY": "doorway_agents_dashboard.anthropic_api_key",
    "VICIDIAL_DB_HOST": "doorway_agents_dashboard.vicidial_db_host",
    "VICIDIAL_DB_PORT": "doorway_agents_dashboard.vicidial_db_port",
    "VICIDIAL_DB_USER": "doorway_agents_dashboard.vicidial_db_user",
    "VICIDIAL_DB_PASSWORD": "doorway_agents_dashboard.vicidial_db_password",
    "VICIDIAL_DB_NAME": "doorway_agents_dashboard.vicidial_db_name",
    "DOORWAY_AGENTS_WEBHOOK_KEY": "doorway_agents_dashboard.webhook_token",
}

ICP_LEGACY_PREFIX = "doorway_agents_ia."

ICP_FALLBACKS = {
    "doorway_agents_dashboard.elevenlabs_api_key": [
        "doorway_agents_ia.elevenlabs_api_key",
        "renovation_conciergerie.elevenlabs_api_key",
    ],
    "doorway_agents_dashboard.elevenlabs_from_number": [
        "doorway_agents_ia.twilio_phone_number",
        "doorway_agents_dashboard.twilio_phone_number",
        "renovation_conciergerie.retell_from_number",
    ],
    "doorway_agents_dashboard.twilio_account_sid": [
        "doorway_agents_ia.twilio_account_sid",
    ],
    "doorway_agents_dashboard.twilio_auth_token": [
        "doorway_agents_ia.twilio_auth_token",
    ],
    "doorway_agents_dashboard.twilio_phone_number": [
        "doorway_agents_ia.twilio_phone_number",
    ],
    "doorway_agents_dashboard.anthropic_api_key": [
        "doorway_agents_ia.anthropic_api_key",
        "renovation_conciergerie.anthropic_api_key",
    ],
    "doorway_agents_dashboard.vicidial_db_host": ["doorway_agents_ia.vicidial_db_host"],
    "doorway_agents_dashboard.vicidial_db_port": ["doorway_agents_ia.vicidial_db_port"],
    "doorway_agents_dashboard.vicidial_db_user": ["doorway_agents_ia.vicidial_db_user"],
    "doorway_agents_dashboard.vicidial_db_password": [
        "doorway_agents_ia.vicidial_db_password"
    ],
    "doorway_agents_dashboard.vicidial_db_name": ["doorway_agents_ia.vicidial_db_name"],
}


def pre_init_hook(cr):
    """Préserve les FK sessions → agent.ia avant changement de comodel sur agent_id."""
    if not sql.table_exists(cr, "doorway_call_session"):
        return
    if sql.column_exists(cr, "doorway_call_session", "legacy_agent_ia_id"):
        return
    if not sql.column_exists(cr, "doorway_call_session", "agent_id"):
        return
    cr.execute(
        """
        ALTER TABLE doorway_call_session
        RENAME COLUMN agent_id TO legacy_agent_ia_id
        """
    )
    _logger.info(
        "doorway_agents_dashboard: colonne agent_id → legacy_agent_ia_id (migration fusion)"
    )


def _sync_env_to_icp(env):
    icp = env["ir.config_parameter"].sudo()
    conf_vals = load_conf_values()
    updated = []
    for env_key, param_key in ENV_TO_ICP.items():
        if icp.get_param(param_key):
            continue
        value = os.environ.get(env_key) or conf_vals.get(env_key)
        if not value:
            for fb in ICP_FALLBACKS.get(param_key, ()):
                value = icp.get_param(fb)
                if value:
                    break
        if value:
            icp.set_param(param_key, value)
            updated.append(param_key)
    if not icp.get_param("doorway_agents_dashboard.webhook_token"):
        icp.set_param("doorway_agents_dashboard.webhook_token", secrets.token_hex(32))
        updated.append("doorway_agents_dashboard.webhook_token")
    if updated:
        _logger.info(
            "doorway_agents_dashboard: paramètres config → %s",
            ", ".join(updated),
        )


def _migrate_icp_from_agents_ia(env):
    icp = env["ir.config_parameter"].sudo()
    cr = env.cr
    cr.execute(
        """
        SELECT key, value FROM ir_config_parameter
        WHERE key LIKE %s
        """,
        (ICP_LEGACY_PREFIX + "%",),
    )
    for old_key, value in cr.fetchall():
        if not value:
            continue
        suffix = old_key[len(ICP_LEGACY_PREFIX) :]
        new_key = f"doorway_agents_dashboard.{suffix}"
        if not icp.get_param(new_key):
            icp.set_param(new_key, value)
            _logger.info("doorway_agents_dashboard: ICP migré %s → %s", old_key, new_key)


def _reparent_agents_ia_xml_ids(env):
    """Évite la perte des menus/actions lors de la désinstallation de doorway_agents_ia."""
    env.cr.execute(
        """
        UPDATE ir_model_data
        SET module = 'doorway_agents_dashboard'
        WHERE module = 'doorway_agents_ia'
        """
    )
    if env.cr.rowcount:
        _logger.info(
            "doorway_agents_dashboard: %s enregistrements ir.model.data reparentés",
            env.cr.rowcount,
        )


def _profile_from_agent_ia(env, ia):
    Profile = env["doorway.agent.profile"].sudo()
    ext_id = (ia.elevenlabs_agent_id or ia.code or "").strip()
    profile = Profile.browse()
    if ext_id:
        profile = Profile.search([("external_agent_id", "=", ext_id)], limit=1)
    if not profile:
        profile = Profile.search([("name", "=", ia.name)], limit=1)
    if not profile:
        profile = Profile.create(
            {
                "name": ia.name,
                "provider": "elevenlabs" if ia.elevenlabs_agent_id else "n8n",
                "external_agent_id": ext_id or f"legacy-ia-{ia.id}",
                "pipeline": ia.pipeline if ia.pipeline in dict(Profile._fields["pipeline"].selection) else "doorway",
                "agent_type": ia.agent_type,
                "language": "fr" if ia.langue == "fr" else ("en" if ia.langue == "en" else "bilingual"),
                "system_prompt": ia.system_prompt,
            }
        )
    return profile


def _migrate_call_sessions_to_profiles(env):
    if not sql.table_exists(env.cr, "doorway_call_session"):
        return
    Session = env["doorway.call.session"].sudo()
    AgentIa = env["doorway.agent.ia"].sudo()
    mapping = {ia.id: _profile_from_agent_ia(env, ia).id for ia in AgentIa.search([])}
    if sql.column_exists(env.cr, "doorway_call_session", "legacy_agent_ia_id"):
        for sess in Session.search([("agent_id", "=", False), ("legacy_agent_ia_id", "!=", False)]):
            prof_id = mapping.get(sess.legacy_agent_ia_id.id)
            if prof_id:
                sess.agent_id = prof_id
    elif mapping:
        for sess in Session.search([("agent_id", "!=", False)]):
            aid = sess.agent_id.id
            if aid in mapping:
                sess.agent_id = mapping[aid]


def _deactivate_legacy_agents_ia_module(env):
    mod = env["ir.module.module"].sudo().search([("name", "=", "doorway_agents_ia")], limit=1)
    if not mod or mod.state != "installed":
        return
    try:
        mod.button_immediate_uninstall()
        _logger.info("doorway_agents_dashboard: module doorway_agents_ia désinstallé")
    except Exception:  # noqa: BLE001
        _logger.warning(
            "doorway_agents_dashboard: désinstallation doorway_agents_ia reportée "
            "(désinstallez manuellement depuis Apps après vérification)",
            exc_info=True,
        )


def post_init_hook(env):
    try:
        _sync_env_to_icp(env)
        _migrate_icp_from_agents_ia(env)
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_agents_dashboard: sync config env")
    try:
        _reparent_agents_ia_xml_ids(env)
        _migrate_call_sessions_to_profiles(env)
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_agents_dashboard: migration agents_ia")
    try:
        env["doorway.agent.profile"].cron_sync_agents()
        _logger.info("doorway_agents_dashboard: sync initiale agents OK")
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_agents_dashboard: sync initiale agents")
    try:
        env["doorway.agent.profile"]._post_init_maison_recherchee()
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_agents_dashboard: sync immo Maison Recherchée")
    try:
        agents = env["doorway.agent.profile"].sudo().search(
            [("allow_availability_check", "=", True)]
        )
        agents._ensure_calendar_user()
        env["res.users"].sudo().doorway_sync_calendar_filters()
        _logger.info("doorway_agents_dashboard: calendriers agents synchronisés")
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_agents_dashboard: sync calendriers agents")
    _deactivate_legacy_agents_ia_module(env)
