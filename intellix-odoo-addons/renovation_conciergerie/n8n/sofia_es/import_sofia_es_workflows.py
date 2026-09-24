#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importe les workflows Sofia Espagne (VICIdial + TrustSIP) dans n8n."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

SOFIA_DIR = Path(__file__).resolve().parent
WORKFLOWS_DIR = SOFIA_DIR / "workflows"
CONF = Path("/etc/odoo-server.conf")
N8N_ENV = Path("/opt/n8n/.env")

IMPORT_ORDER = [
    "04_google_sheets.json",
    "03_conversation_engine.json",
    "02_vicidial_events.json",
    "01_outbound_vicidial.json",
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


def _build_env_map() -> dict[str, str]:
    base_url = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    vic_base = (_read_conf("VICIDIAL_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
    if "127.0.0.1" in vic_base or "localhost" in vic_base:
        vic_base = "http://187.124.50.69:8080"
    return {
        "TELEPHONY_PROVIDER": "vicidial",
        "VICIDIAL_API_URL": _read_conf("VICIDIAL_API_URL")
        or (vic_base + "/vicidial/non_agent_api.php"),
        "VICIDIAL_USER": _read_conf("VICIDIAL_API_USER") or _read_conf("VICIDIAL_USER"),
        "VICIDIAL_PASS": _read_conf("VICIDIAL_API_PASS") or _read_conf("VICIDIAL_PASS"),
        "VICIDIAL_CAMPAIGN": "DW_ESREN",
        "SIP_PHONE_NUMBER": _read_conf("SIP_PHONE_NUMBER") or "+349XXXXXXXX",
        "N8N_WEBHOOK_URL": _read_conf("N8N_WEBHOOK_URL") or (base_url + "/webhook"),
        "DEEPGRAM_API_KEY": _read_conf("DEEPGRAM_API_KEY"),
        "ANTHROPIC_API_KEY": _read_conf("ANTHROPIC_API_KEY")
        or _icp("doorway_agents_dashboard.anthropic_api_key"),
        "ELEVENLABS_API_KEY": _read_conf("ELEVENLABS_API_KEY"),
        "ELEVENLABS_VOICE_ID": _read_conf("ELEVENLABS_VOICE_ID")
        or _icp("doorway_agents_dashboard.elevenlabs_voice_id_sophie"),
        "GOOGLE_SHEETS_ID": _read_conf("GOOGLE_SHEETS_ID")
        or _icp("doorway_agents_dashboard.google_sheets_spreadsheet_id"),
        "GOOGLE_SHEETS_WEBHOOK_URL": _read_conf("GOOGLE_SHEETS_WEBHOOK_URL")
        or _icp("doorway_agents_dashboard.google_sheets_webhook_url"),
        "GOOGLE_SHEETS_TAB": "Leads_Sofia_Espagne",
        "STORAGE_BUCKET_URL": _read_conf("STORAGE_BUCKET_URL")
        or "https://intellixcrm.com/sofia-es-tts",
        "CAMPAIGN_ID": "sofia-es-avatrade-2026",
        "AGENT_MAX_SEC": _read_conf("AGENT_MAX_SEC") or "120",
        "AGENT_SOFT_LIMIT_SEC": _read_conf("AGENT_SOFT_LIMIT_SEC") or "110",
        "SOFIA_STT_BYPASS": _read_conf("SOFIA_STT_BYPASS") or "false",
        "SOFIA_RECORD_PAUSE_SEC": _read_conf("SOFIA_RECORD_PAUSE_SEC") or "2",
        "SOFIA_RECORD_TIMEOUT": _read_conf("SOFIA_RECORD_TIMEOUT") or "5",
        "SOFIA_RECORD_MAXLENGTH": _read_conf("SOFIA_RECORD_MAXLENGTH") or "10",
        "ODOO_URL": _read_conf("ODOO_URL") or "https://intellixcrm.com",
        "DOORWAY_TENANT_API_KEY": _read_conf("DOORWAY_TENANT_API_KEY")
        or _icp("doorway_credits.tenant_api_key")
        or subprocess.check_output(
            [
                "sudo", "-u", "odoo", "psql", "-d", "intellixcrm", "-tAc",
                "SELECT api_key FROM doorway_tenant ORDER BY id LIMIT 1;",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        or _read_conf("DOORWAY_AGENTS_WEBHOOK_KEY"),
        "SOFIA_BILLING_RATE": "0.22",
        "SOFIA_AMD_ENABLED": "true",
    }


def sync_n8n_env(env_map: dict[str, str]) -> None:
    if not N8N_ENV.is_file():
        print(f"WARN: {N8N_ENV} introuvable", file=sys.stderr)
        return
    text = N8N_ENV.read_text(encoding="utf-8")
    marker_start = "# --- sofia-es vicidial ---"
    marker_end = "# --- end sofia-es ---"
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
            timeout=120,
        )
        action = "updated"
    else:
        r = requests.post(
            f"{api_base}/api/v1/workflows",
            headers=headers,
            json=payload,
            timeout=120,
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


def main() -> None:
    token = _read_conf("N8N_API_TOKEN")
    if not token:
        print("N8N_API_TOKEN manquant", file=sys.stderr)
        sys.exit(1)
    api_base = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    headers = {"X-N8N-API-KEY": token, "Content-Type": "application/json"}

    sync_script = SOFIA_DIR / "sync_workflow_code.py"
    subprocess.run([sys.executable, str(sync_script)], check=True)

    env_map = _build_env_map()
    sync_n8n_env(env_map)

    print(f"Import Sofia ES → {api_base}")
    for fname in IMPORT_ORDER:
        path = WORKFLOWS_DIR / fname
        if not path.is_file():
            print(f"  skip: {fname}")
            continue
        import_workflow(api_base, headers, path)
    print("Done. Webhooks: /webhook/sofia-es/{outbound,vicidial/event,conversation,sheets}")


if __name__ == "__main__":
    main()
