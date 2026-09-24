#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importe les workflows Sofia RénoFacile FR (VICIdial DW_FRB2C) dans n8n."""
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


def _icp(key: str) -> str:
    try:
        return subprocess.check_output(
            ["sudo", "-u", "odoo", "psql", "-d", "intellixcrm", "-tAc",
             f"SELECT COALESCE(value,'') FROM ir_config_parameter WHERE key='{key}';"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return ""


def _build_env_map() -> dict[str, str]:
    base = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    vic_base = (_read_conf("VICIDIAL_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
    if "127.0.0.1" in vic_base or "localhost" in vic_base:
        vic_base = "http://187.124.50.69:8080"
    return {
        "TELEPHONY_PROVIDER": "vicidial",
        "VICIDIAL_API_URL": _read_conf("VICIDIAL_API_URL") or (vic_base + "/vicidial/non_agent_api.php"),
        "VICIDIAL_USER": _read_conf("VICIDIAL_API_USER") or _read_conf("VICIDIAL_USER"),
        "VICIDIAL_PASS": _read_conf("VICIDIAL_API_PASS") or _read_conf("VICIDIAL_PASS"),
        "VICIDIAL_CAMPAIGN": "DW_FRB2C",
        "VICIDIAL_LIST": "1004",
        "AGENT_ID": "marenofacile",
        "SIP_PHONE_NUMBER": _read_conf("SIP_PHONE_NUMBER") or "15817058118",
        "N8N_WEBHOOK_URL": _read_conf("N8N_WEBHOOK_URL") or (base + "/webhook"),
        "DEEPGRAM_API_KEY": _read_conf("DEEPGRAM_API_KEY"),
        "ANTHROPIC_API_KEY": _read_conf("ANTHROPIC_API_KEY") or _icp("doorway_agents_dashboard.anthropic_api_key"),
        "ELEVENLABS_API_KEY": _read_conf("ELEVENLABS_API_KEY"),
        "ELEVENLABS_VOICE_ID": _read_conf("ELEVENLABS_VOICE_ID"),
        "STORAGE_BUCKET_URL": _read_conf("STORAGE_BUCKET_URL") or "https://intellixcrm.com/renofacile-fr-tts",
        "AGENT_MAX_SEC": "120",
        "AGENT_SOFT_LIMIT_SEC": "110",
        "SOFIA_STT_WEBHOOK_KEY": _read_conf("SOFIA_STT_WEBHOOK_KEY") or "doorway-sofia-stt",
        "ODOO_URL": _read_conf("ODOO_URL") or "https://intellixcrm.com",
        "DOORWAY_TENANT_API_KEY": _read_conf("DOORWAY_TENANT_API_KEY")
        or _icp("doorway_credits.tenant_api_key")
        or subprocess.check_output(
            ["sudo", "-u", "odoo", "psql", "-d", "intellixcrm", "-tAc",
             "SELECT api_key FROM doorway_tenant ORDER BY id LIMIT 1;"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip(),
    }


def sync_n8n_env(env_map: dict[str, str]) -> None:
    if not N8N_ENV.is_file():
        print(f"WARN: {N8N_ENV} missing", file=sys.stderr)
        return
    start, end = "# --- renofacile-fr vicidial ---", "# --- end renofacile-fr ---"
    block = start + "\n" + "\n".join(f"{k}={v or ''}" for k, v in env_map.items()) + "\n" + end + "\n"
    text = N8N_ENV.read_text(encoding="utf-8")
    if start in text:
        text = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n?", block, text, flags=re.DOTALL)
    else:
        text = text.rstrip() + "\n\n" + block
    N8N_ENV.write_text(text, encoding="utf-8")
    print(f"Variables sync → {N8N_ENV}")


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
        r = requests.put(f"{api_base}/api/v1/workflows/{wf_id}", headers=headers, json=payload, timeout=120)
        action = "updated"
    else:
        r = requests.post(f"{api_base}/api/v1/workflows", headers=headers, json=payload, timeout=120)
        action = "created"
    if r.status_code >= 400:
        raise RuntimeError(f"{path.name}: {r.status_code} {r.text[:600]}")
    wf_id = r.json().get("id") or existing.get(payload["name"])
    act = requests.post(f"{api_base}/api/v1/workflows/{wf_id}/activate", headers=headers, timeout=30)
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

    subprocess.run([sys.executable, str(ROOT / "bootstrap_workflows.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "sync_workflow_code.py")], check=True)

    sync_n8n_env(_build_env_map())

    print(f"Import RénoFacile FR → {api_base}")
    ids = {}
    for fname in IMPORT_ORDER:
        path = WF / fname
        if not path.is_file():
            print(f"  skip: {fname}")
            continue
        ids[fname] = import_workflow(api_base, headers, path)
    print("Done. Webhooks: /webhook/renofacile-fr/{outbound,event,conversation}")
    print("Odoo: POST /doorway/api/renofacile-fr/call-ended")


if __name__ == "__main__":
    main()
