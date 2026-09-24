#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importe les workflows renov-aides dans n8n + sync variables .env."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

RENOV_DIR = Path(__file__).resolve().parent
WORKFLOWS_DIR = RENOV_DIR / "workflows"
CONF = Path("/etc/odoo-server.conf")
N8N_ENV = Path("/opt/n8n/.env")

IMPORT_ORDER = [
    "utils_elevenlabs_tts.json",
    "05_google_sheets_writer.json",
    "adapter_twilio.json",
    "adapter_telnyx.json",
    "adapter_vicidial.json",
    "03_conversation_engine.json",
    "01_outbound_trigger.json",
]


def _read_conf(key: str) -> str:
    if not CONF.is_file():
        return ""
    for line in CONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
        if line.startswith(f";{key}="):
            val = line.split("=", 1)[1].strip()
            if val:
                return val
    return ""


def _icp(key: str) -> str:
    try:
        out = subprocess.check_output(
            [
                "sudo",
                "-u",
                "odoo",
                "psql",
                "-d",
                "intellixcrm",
                "-tAc",
                f"SELECT COALESCE(value,'') FROM ir_config_parameter WHERE key='{key}';",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except subprocess.CalledProcessError:
        return ""


def _anthropic_key() -> str:
    return (
        _icp("doorway_agents_dashboard.anthropic_api_key")
        or _icp("renovation_conciergerie.anthropic_api_key")
        or _read_conf("ANTHROPIC_API_KEY")
    )


def _build_env_map() -> dict[str, str]:
    base_url = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    vic_base = (_read_conf("VICIDIAL_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
    if "127.0.0.1" in vic_base or "localhost" in vic_base:
        vic_base = "http://187.124.50.69:8080"
    return {
        "TELEPHONY_PROVIDER": _read_conf("TELEPHONY_PROVIDER") or "twilio",
        "TWILIO_ACCOUNT_SID": _read_conf("TWILIO_ACCOUNT_SID"),
        "TWILIO_AUTH_TOKEN": _read_conf("TWILIO_AUTH_TOKEN"),
        "TWILIO_PHONE_NUMBER": _read_conf("TWILIO_PHONE_NUMBER")
        or _read_conf("TWILIO_FROM_NUMBER"),
        "TELNYX_API_KEY": _read_conf("TELNYX_API_KEY"),
        "TELNYX_PHONE_NUMBER": _read_conf("TELNYX_PHONE_NUMBER"),
        "TELNYX_CONNECTION_ID": _read_conf("TELNYX_CONNECTION_ID"),
        "VICIDIAL_API_URL": _read_conf("VICIDIAL_API_URL")
        or (vic_base + "/vicidial/non_agent_api.php"),
        "VICIDIAL_USER": _read_conf("VICIDIAL_API_USER") or _read_conf("VICIDIAL_USER"),
        "VICIDIAL_PASS": _read_conf("VICIDIAL_API_PASS") or _read_conf("VICIDIAL_PASS"),
        "VICIDIAL_CAMPAIGN": _read_conf("VICIDIAL_CAMPAIGN") or "renov_es",
        "SIP_PHONE_NUMBER": _read_conf("SIP_PHONE_NUMBER") or _read_conf("TWILIO_FROM_NUMBER"),
        "N8N_WEBHOOK_URL": _read_conf("N8N_WEBHOOK_URL") or (base_url + "/webhook"),
        "DEEPGRAM_API_KEY": _read_conf("DEEPGRAM_API_KEY"),
        "ANTHROPIC_API_KEY": _anthropic_key(),
        "ELEVENLABS_API_KEY": _read_conf("ELEVENLABS_API_KEY"),
        "ELEVENLABS_VOICE_ID": _read_conf("ELEVENLABS_VOICE_ID")
        or _icp("doorway_agents_dashboard.elevenlabs_voice_id_sophie"),
        "GOOGLE_SHEETS_ID": _read_conf("GOOGLE_SHEETS_ID")
        or _icp("doorway_agents_dashboard.google_sheets_spreadsheet_id"),
        "GOOGLE_SHEETS_SHEET_NAME": _read_conf("GOOGLE_SHEETS_SHEET_NAME")
        or _icp("doorway_agents_dashboard.google_sheets_sheet_name")
        or "Appels IA",
        "GOOGLE_API_KEY": _read_conf("GOOGLE_API_KEY")
        or _icp("doorway_agents_dashboard.google_api_key"),
        "GOOGLE_SHEETS_WEBHOOK_URL": _read_conf("GOOGLE_SHEETS_WEBHOOK_URL")
        or _icp("doorway_agents_dashboard.google_sheets_webhook_url"),
        "STORAGE_BUCKET_URL": _read_conf("STORAGE_BUCKET_URL")
        or "https://intellixcrm.com/sofia-tts",
        "CAMPAIGN_ID": _read_conf("CAMPAIGN_ID") or "sofia-test-maroc-juin2026",
        "GOOGLE_SHEETS_TAB": _read_conf("GOOGLE_SHEETS_TAB")
        or _read_conf("GOOGLE_SHEETS_SHEET_NAME")
        or "Leads_Sofia_Test",
        "AGENT_MAX_SEC": _read_conf("AGENT_MAX_SEC") or "120",
        "AGENT_SOFT_LIMIT_SEC": _read_conf("AGENT_SOFT_LIMIT_SEC") or "110",
        "SOFIA_STT_BYPASS": _read_conf("SOFIA_STT_BYPASS") or "false",
        "SOFIA_STT_DELAY_MS": _read_conf("SOFIA_STT_DELAY_MS") or "0",
        "SOFIA_RECORD_PAUSE_SEC": _read_conf("SOFIA_RECORD_PAUSE_SEC") or "2",
        "SOFIA_RECORD_TIMEOUT": _read_conf("SOFIA_RECORD_TIMEOUT") or "5",
        "SOFIA_RECORD_MAXLENGTH": _read_conf("SOFIA_RECORD_MAXLENGTH") or "10",
        "ODOO_URL": _read_conf("ODOO_URL") or "https://intellixcrm.com",
        "SOFIA_STT_WEBHOOK_KEY": _read_conf("SOFIA_STT_WEBHOOK_KEY")
        or _read_conf("renovation_conciergerie.sofia_stt_key")
        or "doorway-sofia-stt",
    }


def sync_n8n_env(env_map: dict[str, str]) -> None:
    """Met à jour /opt/n8n/.env section renov-aides."""
    if not N8N_ENV.is_file():
        print(f"WARN: {N8N_ENV} introuvable", file=sys.stderr)
        return
    text = N8N_ENV.read_text(encoding="utf-8")
    marker_start = "# --- renov-aides outbound v2 ---"
    marker_end = "# --- end renov-aides ---"
    block_lines = [marker_start]
    for key, val in env_map.items():
        safe = (val or "").replace("\n", "\\n")
        block_lines.append(f"{key}={safe}")
    block_lines.append(marker_end)
    block = "\n".join(block_lines) + "\n"
    if marker_start in text:
        text = re.sub(
            re.escape(marker_start) + r".*?" + re.escape(marker_end) + r"\n?",
            block,
            text,
            flags=re.DOTALL,
        )
    else:
        text = text.rstrip() + "\n\n" + block
    N8N_ENV.write_text(text, encoding="utf-8")
    print(f"Variables sync → {N8N_ENV} ({len(env_map)} clés)")


def _prepare_workflow(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for node in data.get("nodes", []):
        node.pop("id", None)
        node.pop("credentials", None)
    return {
        "name": data["name"],
        "nodes": data["nodes"],
        "connections": data["connections"],
        "settings": data.get("settings") or {"executionOrder": "v1"},
    }


def _list_workflows(api_base: str, headers: dict) -> dict[str, str]:
    by_name = {}
    cursor = None
    while True:
        url = f"{api_base}/api/v1/workflows?limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        for w in body.get("data", []):
            by_name[w["name"]] = w["id"]
        cursor = body.get("nextCursor")
        if not cursor:
            break
    return by_name


def import_workflow(api_base: str, headers: dict, path: Path) -> str:
    payload = _prepare_workflow(path)
    existing = _list_workflows(api_base, headers)
    if payload["name"] in existing:
        wf_id = existing[payload["name"]]
        r = requests.put(
            f"{api_base}/api/v1/workflows/{wf_id}",
            headers=headers,
            json=payload,
            timeout=90,
        )
        action = "updated"
    else:
        r = requests.post(
            f"{api_base}/api/v1/workflows",
            headers=headers,
            json=payload,
            timeout=90,
        )
        action = "created"
    if r.status_code >= 400:
        raise RuntimeError(f"{path.name}: {r.status_code} {r.text[:600]}")
    wf_id = r.json().get("id") or existing.get(payload["name"])
    act = requests.post(
        f"{api_base}/api/v1/workflows/{wf_id}/activate",
        headers=headers,
        timeout=30,
    )
    status = "actif" if act.status_code < 400 else f"non activé ({act.status_code})"
    print(f"  {action} + {status}: {payload['name']} ({wf_id})")
    return wf_id


def main():
    token = _read_conf("N8N_API_TOKEN")
    if not token:
        print("N8N_API_TOKEN manquant", file=sys.stderr)
        sys.exit(1)
    api_base = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    headers = {"X-N8N-API-KEY": token, "Content-Type": "application/json"}

    env_map = _build_env_map()
    sync_n8n_env(env_map)

    missing = [k for k, v in env_map.items() if not v and k in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "ELEVENLABS_API_KEY",
        "ANTHROPIC_API_KEY", "DEEPGRAM_API_KEY",
    )]
    if missing:
        print(f"WARN: variables vides (à compléter): {', '.join(missing)}", file=sys.stderr)

    sync_script = RENOV_DIR / "sync_workflow_code.py"
    if sync_script.is_file():
        import subprocess
        subprocess.run([sys.executable, str(sync_script)], check=True)

    print(f"Import renov-aides → {api_base}")
    for fname in IMPORT_ORDER:
        path = WORKFLOWS_DIR / fname
        if not path.is_file():
            print(f"  skip: {fname}")
            continue
        try:
            import_workflow(api_base, headers, path)
        except Exception as exc:
            print(f"  ERROR {fname}: {exc}", file=sys.stderr)
            sys.exit(1)
    print(
        "Done. Si .env modifié: cd /opt/n8n && docker compose up -d --force-recreate n8n"
    )


if __name__ == "__main__":
    main()
