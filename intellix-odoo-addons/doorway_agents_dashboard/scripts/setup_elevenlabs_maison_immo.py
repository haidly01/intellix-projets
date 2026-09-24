#!/usr/bin/env python3
"""Setup ElevenLabs Sophie — voix + qualification + 4 agents relance."""
import json
import os
import sys

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VOICE_FILE = os.path.join(ROOT, "voice_samples", "Rue_Ibnou_Jahir_3.m4a")
BASE = "https://api.elevenlabs.io/v1"
IDS_FILE = os.path.join(ROOT, "voice_samples", "elevenlabs_ids.json")

sys.path.insert(0, os.path.join(ROOT, "services"))
from elevenlabs_maison_immo import SOPHIE_FIRST_MESSAGE, SOPHIE_SYSTEM_PROMPT  # noqa: E402
from elevenlabs_maison_immo_relance import RELANCE_AGENT_SPECS  # noqa: E402


def _read_prompt():
    path = os.path.join(ROOT, "services", "elevenlabs_maison_immo.py")
    with open(path, encoding="utf-8") as handle:
        return handle.read().split('SOPHIE_SYSTEM_PROMPT = """')[1].split('"""')[0]


def _tts(voice_id, stability=0.5):
    return {
        "voice_id": voice_id,
        "model_id": "eleven_turbo_v2_5",
        "optimize_streaming_latency": 4,
        "stability": stability,
        "similarity_boost": 0.85,
    }


def create_agent(headers, name, prompt, first_message, voice_id, max_duration, **agent_kw):
    payload = {
        "name": name,
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": prompt,
                    "llm": "claude-3-5-sonnet",
                    "temperature": agent_kw.get("temperature", 0.4),
                    "max_tokens": agent_kw.get("max_tokens", 200),
                },
                "first_message": first_message,
                "language": "fr",
            },
            "tts": _tts(voice_id, agent_kw.get("stability", 0.5)),
            "turn": {
                "turn_timeout": agent_kw.get("turn_timeout", 8),
                "silence_end_call_timeout": agent_kw.get("silence_end_call_timeout", 18),
            },
            "conversation": {"max_duration_seconds": max_duration},
        },
    }
    r = requests.post(f"{BASE}/convai/agents/create", headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        r = requests.post(
            f"{BASE}/convai/agents/create",
            headers=headers,
            json={"name": name, "conversation_config": payload["conversation_config"]},
            timeout=60,
        )
    if r.status_code != 200:
        print(f"❌ {name}: {r.status_code} {r.text[:400]}")
        return ""
    aid = r.json().get("agent_id", "")
    print(f"   ✅ {name}: {aid}")
    return aid


def main():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("❌ ELEVENLABS_API_KEY requis")
        sys.exit(1)

    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    voice_id = None
    if os.path.isfile(IDS_FILE):
        voice_id = json.load(open(IDS_FILE, encoding="utf-8")).get("voice_id")

    if not voice_id and os.path.isfile(VOICE_FILE):
        print("📢 Clone vocal...")
        with open(VOICE_FILE, "rb") as handle:
            r1 = requests.post(
                f"{BASE}/voices/add",
                headers={"xi-api-key": api_key},
                data={
                    "name": "Sophie — Agent Immo Doorway",
                    "description": "Qualification immo QC",
                    "labels": json.dumps({"accent": "canadian_french", "project": "doorway_immo"}),
                },
                files=[("files", ("Rue_Ibnou_Jahir_3.m4a", handle.read(), "audio/mp4"))],
                timeout=120,
            )
        if r1.status_code != 200:
            print(f"❌ voix {r1.status_code} {r1.text[:300]}")
            sys.exit(1)
        voice_id = r1.json()["voice_id"]
        print(f"   voice_id={voice_id}")
    elif not voice_id:
        print(f"❌ Placer audio dans {VOICE_FILE} ou voice_id dans {IDS_FILE}")
        sys.exit(1)

    prompt = _read_prompt()
    print("🤖 Agent qualification...")
    agent_id = create_agent(
        headers,
        "Sophie — Qualification Immo Doorway",
        prompt,
        SOPHIE_FIRST_MESSAGE,
        voice_id,
        480,
        temperature=0.4,
        max_tokens=300,
    )

    print("🔄 Agents relance J+1 / J+3 / J+7 / J+14...")
    relance_agents = {}
    for spec in RELANCE_AGENT_SPECS:
        aid = create_agent(
            headers,
            spec["odoo_name"],
            spec["prompt"],
            spec["first_message"],
            voice_id,
            spec["max_duration_seconds"],
            temperature=spec.get("temperature", 0.35),
            max_tokens=spec.get("max_tokens", 200),
            stability=spec.get("stability", 0.5),
            turn_timeout=spec.get("turn_timeout", 8),
            silence_end_call_timeout=spec.get("silence_end_call_timeout", 18),
        )
        if aid:
            relance_agents[spec["key"]] = aid

    out = {
        "voice_id": voice_id,
        "agent_id": agent_id,
        "relance_agents": relance_agents,
        "sip_trunk_sid": "TK4005d66df6aefef66f0a63a711491166",
        "from_number": "+14387905970",
        "transfer_number": "+14389929200",
        "env_mapping": {
            "ELEVENLABS_AGENT_ID_IMMO": agent_id,
            "ELEVENLABS_AGENT_ID_RELANCE_J1": relance_agents.get("j1", ""),
            "ELEVENLABS_AGENT_ID_RELANCE_J3": relance_agents.get("j3", ""),
            "ELEVENLABS_AGENT_ID_RELANCE_J7": relance_agents.get("j7", ""),
            "ELEVENLABS_AGENT_ID_RELANCE_J14": relance_agents.get("j14", ""),
        },
    }
    with open(IDS_FILE, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, ensure_ascii=False)
    print(f"✅ {IDS_FILE}")
    print("\nVariables n8n:")
    for k, v in out["env_mapping"].items():
        if v:
            print(f"  {k}={v}")


if __name__ == "__main__":
    main()
