#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importe les workflows Sofia Soumission QC dans n8n."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
WF = ROOT / "workflows"
CONF = Path("/etc/odoo-server.conf")
N8N_ENV = Path("/opt/n8n/.env")

IMPORT_ORDER = [
    "06_daily_stats.json",
    "05_non_qualified_lead.json",
    "04_qualified_lead.json",
    "03_conversation_engine.json",
    "02_telephony_events.json",
    "01_outbound.json",
]


def _read_conf(key: str) -> str:
    if not CONF.is_file():
        return ""
    for line in CONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _build_env_map() -> dict[str, str]:
    base = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    return {
        "TELEPHONY_PROVIDER": "vicidial",
        "VICIDIAL_CAMPAIGN": "DW_QCB2C",
        "VICIDIAL_LIST": "DW_QCB2C",
        "CAMPAIGN_ID": "lea-qc-2026",
        "N8N_BASE_URL": base,
        "N8N_WEBHOOK_URL": _read_conf("N8N_WEBHOOK_URL") or (base + "/webhook"),
        "ODOO_URL": _read_conf("ODOO_URL") or "https://intellixcrm.com",
        "STORAGE_BUCKET_URL": "https://intellixcrm.com/lea-qc-tts",
        "AGENT_SOFT_LIMIT_SEC": "170",
        "SOFIA_QC_RATE_PER_MIN": "0.25",
        "TWILIO_FROM_SOUMISSION": "+15817058118",
        "DEEPGRAM_API_KEY": _read_conf("DEEPGRAM_API_KEY"),
        "ANTHROPIC_API_KEY": _read_conf("ANTHROPIC_API_KEY"),
        "ELEVENLABS_API_KEY": _read_conf("ELEVENLABS_API_KEY"),
        "ELEVENLABS_VOICE_ID": _read_conf("ELEVENLABS_VOICE_ID"),
        "TWILIO_ACCOUNT_SID": _read_conf("TWILIO_ACCOUNT_SID"),
        "TWILIO_AUTH_TOKEN": _read_conf("TWILIO_AUTH_TOKEN"),
        "DOORWAY_TENANT_API_KEY": _read_conf("DOORWAY_TENANT_API_KEY"),
        "DIRECTOR_EMAIL": "karine@agencedoorway.com",
        "MANAGER_EMAIL": "karine@agencedoorway.com",
    }


def sync_n8n_env(env_map: dict[str, str]) -> None:
    if not N8N_ENV.is_file():
        print(f"WARN: {N8N_ENV} missing")
        return
    start, end = "# --- lea-qc ---", "# --- end lea-qc ---"
    block = start + "\n" + "\n".join(f"{k}={v or ''}" for k, v in env_map.items()) + "\n" + end + "\n"
    text = N8N_ENV.read_text(encoding="utf-8")
    if start in text:
        text = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n?", block, text, flags=re.DOTALL)
    else:
        text = text.rstrip() + "\n\n" + block
    N8N_ENV.write_text(text, encoding="utf-8")


def import_workflow(api_base: str, headers: dict, path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for node in data.get("nodes", []):
        node.pop("id", None)
    payload = {
        "name": data["name"],
        "nodes": data["nodes"],
        "connections": data["connections"],
        "settings": data.get("settings") or {"executionOrder": "v1"},
    }
    r = requests.get(f"{api_base}/api/v1/workflows?limit=100", headers=headers, timeout=30)
    r.raise_for_status()
    by_name = {w["name"]: w["id"] for w in r.json().get("data", [])}
    if payload["name"] in by_name:
        wf_id = by_name[payload["name"]]
        resp = requests.put(f"{api_base}/api/v1/workflows/{wf_id}", headers=headers, json=payload, timeout=120)
    else:
        resp = requests.post(f"{api_base}/api/v1/workflows", headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    wf_id = resp.json().get("id") or by_name.get(payload["name"])
    requests.post(f"{api_base}/api/v1/workflows/{wf_id}/activate", headers=headers, timeout=30)
    print(f"  OK: {payload['name']}")


def main() -> None:
    token = _read_conf("N8N_API_TOKEN")
    if not token:
        print("N8N_API_TOKEN required", file=sys.stderr)
        sys.exit(1)
    subprocess.run([sys.executable, str(ROOT / "sync_workflow_code.py")], check=True)
    sync_n8n_env(_build_env_map())
    api = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    headers = {"X-N8N-API-KEY": token, "Content-Type": "application/json"}
    for fname in IMPORT_ORDER:
        path = WF / fname
        if path.is_file():
            import_workflow(api, headers, path)
    print("Webhooks: /webhook/lea-qc/{outbound,event,conversation,qualified,non-qualified,stats}")


if __name__ == "__main__":
    main()
