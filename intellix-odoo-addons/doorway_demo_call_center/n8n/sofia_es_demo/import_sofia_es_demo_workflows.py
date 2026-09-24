#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importe les workflows Sofia Espagne DEMO (Abdallah / ABD_DEMO) dans n8n."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

DEMO_DIR = Path(__file__).resolve().parent
WORKFLOWS_DIR = DEMO_DIR / "workflows"
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


def _psql(sql: str) -> str:
    try:
        return subprocess.check_output(
            ["sudo", "-u", "odoo", "psql", "-d", "intellixcrm", "-tAc", sql],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return ""


def _demo_tenant_api_key() -> str:
    key = _psql(
        "SELECT t.api_key FROM doorway_tenant t "
        "JOIN res_company c ON c.id = t.company_id "
        "WHERE t.demo_call_center = true AND c.name ILIKE '%Abdallah%' "
        "ORDER BY t.id LIMIT 1;"
    )
    return key or _read_conf("DOORWAY_DEMO_TENANT_API_KEY")


def _build_env_map() -> dict[str, str]:
    base_url = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    return {
        "DOORWAY_DEMO_TENANT_API_KEY": _demo_tenant_api_key(),
        "VICIDIAL_DEMO_CAMPAIGN": "ABD_DEMO",
        "DEMO_CAMPAIGN_ID": "sofia-es-demo-abdallah",
        "DEMO_AGENT_ID": "sofia-es-demo-abdallah",
        "GOOGLE_SHEETS_TAB_DEMO": "Leads_Sofia_Demo_Abdallah",
        "SOFIA_DEMO_BILLING_RATE": "0.22",
        "N8N_WEBHOOK_URL": _read_conf("N8N_WEBHOOK_URL") or (base_url + "/webhook"),
        "ODOO_URL": _read_conf("ODOO_URL") or "https://intellixcrm.com",
    }


def sync_n8n_env(env_map: dict[str, str]) -> None:
    if not N8N_ENV.is_file():
        print(f"WARN: {N8N_ENV} introuvable", file=sys.stderr)
        return
    text = N8N_ENV.read_text(encoding="utf-8")
    marker_start = "# --- sofia-es-demo abdallah ---"
    marker_end = "# --- end sofia-es-demo ---"
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
    print(f"Variables demo sync → {N8N_ENV}")


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

    subprocess.run([sys.executable, str(DEMO_DIR / "sync_workflow_code.py")], check=True)
    env_map = _build_env_map()
    sync_n8n_env(env_map)

    print(f"Import Sofia ES DEMO → {api_base}")
    for fname in IMPORT_ORDER:
        path = WORKFLOWS_DIR / fname
        if not path.is_file():
            print(f"  skip: {fname}")
            continue
        import_workflow(api_base, headers, path)

    subprocess.run(
        ["bash", "-c", "cd /opt/n8n && docker compose up -d --force-recreate n8n"],
        check=False,
    )
    print(
        "Done. Webhooks demo: /webhook/sofia-es-demo/"
        "{outbound,vicidial/event,conversation,sheets}"
    )


if __name__ == "__main__":
    main()
