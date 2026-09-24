# -*- coding: utf-8 -*-
"""Détection répondeur ElevenLabs — raccrocher sans consommer de crédits inutilement."""

VOICEMAIL_DETECTION_TOOL = {
    "type": "system",
    "name": "voicemail_detection",
    "description": (
        "Raccrocher immédiatement si répondeur, boîte vocale ou message automatisé. "
        "Ne jamais laisser de message vocal — économiser les crédits."
    ),
    "params": {
        "system_tool_type": "voicemail_detection",
        "voicemail_message": None,
    },
}

# Limite la sonnerie avant abandon (Twilio / EL)
TELEPHONY_OUTBOUND_CONFIG = {
    "ringing_timeout_secs": 25,
}


def outbound_system_tools():
    """Outils système pour tous les agents sortants (qualif + relances)."""
    return [dict(VOICEMAIL_DETECTION_TOOL)]


def inject_voicemail_detection(agent_payload):
    """Ajoute voicemail_detection au payload create/patch ConvAI."""
    if not agent_payload:
        return agent_payload
    cc = agent_payload.setdefault("conversation_config", {})
    agent = cc.setdefault("agent", {})
    prompt = agent.setdefault("prompt", {})
    tools = list(prompt.get("tools") or [])
    if not any((t or {}).get("name") == "voicemail_detection" for t in tools):
        tools.append(dict(VOICEMAIL_DETECTION_TOOL))
    prompt["tools"] = tools
    return agent_payload
