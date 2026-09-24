#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importe les workflows n8n Doorway (Haidly + immo/énergie) via API."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

N8N_DIR = Path(__file__).resolve().parent
CONF = Path("/etc/odoo-server.conf")
KEEP_CREDENTIAL_NODE_TYPES = frozenset(
    {"n8n-nodes-base.facebookLeadAdsTrigger"}
)


def _read_conf(key: str) -> str:
    if not CONF.is_file():
        return ""
    for line in CONF.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _icp_token(key: str) -> str:
    import subprocess

    out = subprocess.check_output(
        [
            "sudo",
            "-u",
            "odoo",
            "psql",
            "-d",
            "intellixcrm",
            "-t",
            "-c",
            f"SELECT value FROM ir_config_parameter WHERE key='{key}';",
        ],
        text=True,
    )
    return out.strip()


def _haidly_token() -> str:
    return _icp_token("renovation_conciergerie.haidly_webhook_token")


def _meta_graph_token() -> str:
    import subprocess

    return subprocess.check_output(
        [
            "sudo",
            "-u",
            "odoo",
            "psql",
            "-d",
            "intellixcrm",
            "-tAc",
            "SELECT COALESCE(meta_access_token,'') FROM doorway_veille_config LIMIT 1;",
        ],
        text=True,
    ).strip()


def _substitute(text: str) -> str:
    mapping = {
        "{{HAIDLY_WEBHOOK_TOKEN}}": _haidly_token(),
        "{{META_IMMO_WEBHOOK_TOKEN}}": _icp_token(
            "renovation_conciergerie.meta_immo_webhook_token"
        ),
        "{{ENERGIE_WEBHOOK_TOKEN}}": _icp_token(
            "renovation_conciergerie.energie_webhook_token"
        ),
        "{{META_LEADS_ROUTING_TOKEN}}": _icp_token(
            "renovation_conciergerie.meta_leads_routing_token"
        ),
        "{{MARKETING_META_WEBHOOK_TOKEN}}": _icp_token(
            "renovation_conciergerie.marketing_meta_webhook_token"
        ),
        "{{META_GRAPH_ACCESS_TOKEN}}": _meta_graph_token(),
        "{{ANTHROPIC_API_KEY}}": _read_conf_from_icp("anthropic"),
        "{{ELEVENLABS_API_KEY}}": _read_conf("ELEVENLABS_API_KEY"),
        "{{TWILIO_ACCOUNT_SID}}": _read_conf("TWILIO_ACCOUNT_SID"),
        "{{TWILIO_AUTH_TOKEN}}": _read_conf("TWILIO_AUTH_TOKEN"),
        "{{TWILIO_FROM_IMMO}}": _read_conf("TWILIO_FROM_IMMO")
        or "+14387905970",
        "{{TWILIO_FROM_ENERGIE}}": _read_conf("TWILIO_FROM_ENERGIE")
        or "+15818900456",
        "{{N8N_WEBHOOK_BASE}}": _read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com",
    }
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def _read_conf_from_icp(name: str) -> str:
    import subprocess

    key = f"renovation_conciergerie.{name}_api_key"
    if name == "anthropic":
        key = "renovation_conciergerie.anthropic_api_key"
    out = subprocess.check_output(
        [
            "sudo",
            "-u",
            "odoo",
            "psql",
            "-d",
            "intellixcrm",
            "-t",
            "-c",
            f"SELECT value FROM ir_config_parameter WHERE key='{key}';",
        ],
        text=True,
    ).strip()
    if not out:
        out = subprocess.check_output(
            [
                "sudo",
                "-u",
                "odoo",
                "psql",
                "-d",
                "intellixcrm",
                "-t",
                "-c",
                "SELECT value FROM ir_config_parameter "
                "WHERE key='doorway_agents_dashboard.anthropic_api_key';",
            ],
            text=True,
        ).strip()
    return out


def _prepare_workflow(path: Path) -> dict:
    raw = _substitute(path.read_text(encoding="utf-8"))
    data = json.loads(raw)
    for node in data.get("nodes", []):
        node.pop("id", None)
        creds = node.get("credentials")
        if creds and node.get("type") not in KEEP_CREDENTIAL_NODE_TYPES:
            node.pop("credentials", None)
    payload = {
        "name": data["name"],
        "nodes": data["nodes"],
        "connections": data["connections"],
        "settings": data.get("settings") or {"executionOrder": "v1"},
    }
    if data.get("staticData") is not None:
        payload["staticData"] = data["staticData"]
    return payload


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


def import_workflow(api_base: str, headers: dict, path: Path, activate: bool = True) -> str:
    payload = _prepare_workflow(path)
    existing = _list_workflows(api_base, headers)
    if payload["name"] in existing:
        wf_id = existing[payload["name"]]
        r = requests.put(
            f"{api_base}/api/v1/workflows/{wf_id}",
            headers=headers,
            json=payload,
            timeout=60,
        )
        action = "updated"
    else:
        r = requests.post(
            f"{api_base}/api/v1/workflows",
            headers=headers,
            json=payload,
            timeout=60,
        )
        action = "created"
    if r.status_code >= 400:
        raise RuntimeError(f"{path.name}: {r.status_code} {r.text[:500]}")
    wf_id = r.json().get("id") or existing.get(payload["name"])
    if activate and wf_id:
        act = requests.post(
            f"{api_base}/api/v1/workflows/{wf_id}/activate",
            headers=headers,
            timeout=30,
        )
        if act.status_code >= 400:
            print(
                f"  warning: non activé ({act.status_code}) — "
                f"compléter le nœud Facebook Lead Ads (Form) puis Publish dans n8n",
                file=sys.stderr,
            )
        else:
            print(f"  {action} + actif: {payload['name']} ({wf_id})")
            return wf_id
    print(f"  {action}: {payload['name']} ({wf_id})")
    return wf_id


def main():
    token = _read_conf("N8N_API_TOKEN")
    if not token:
        print("N8N_API_TOKEN manquant dans /etc/odoo-server.conf", file=sys.stderr)
        sys.exit(1)
    api_base = (_read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    headers = {"X-N8N-API-KEY": token, "Content-Type": "application/json"}

    files = [
        "workflow_haidly_orchestrator.json",
        "workflow_haidly_postcall.json",
        "workflow_haidly_relance_orchestrator.json",
        "workflow_haidly_nurture_start.json",
        "workflow_meta_leads_hub.json",
        "workflow_meta_immo_orchestrator.json",
        "workflow_elevenlabs_postcall.json",
        "workflow_immo_relance_orchestrator.json",
        "workflow_immo_nurture_master.json",
        "workflow_energie_orchestrator.json",
        "workflow_elevenlabs_energie_postcall.json",
        "workflow_doorway_morning_call.json",
    ]
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    print(f"Import n8n → {api_base}")
    for fname in files:
        path = N8N_DIR / fname
        if not path.is_file():
            print(f"  skip (missing): {fname}")
            continue
        try:
            import_workflow(api_base, headers, path)
        except Exception as exc:
            print(f"  ERROR {fname}: {exc}", file=sys.stderr)
    print("Done.")


if __name__ == "__main__":
    main()
