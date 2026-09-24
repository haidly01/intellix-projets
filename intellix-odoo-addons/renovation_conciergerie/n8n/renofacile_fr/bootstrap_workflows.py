#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crée les squelettes workflows RénoFacile FR si absents."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WF = ROOT / "workflows"
WF.mkdir(exist_ok=True)

SPECS = [
    ("01_outbound.json", "renofacile-fr — 01 Outbound", "renofacile-fr/outbound", "Outbound Dial"),
    ("02_telephony_events.json", "renofacile-fr — 02 Telephony Events", "renofacile-fr/event", "Telephony Events"),
    ("03_conversation_engine.json", "renofacile-fr — 03 Conversation Engine", "renofacile-fr/conversation", "RénoFacile Engine"),
]


def _wf(name: str, path: str, node_label: str) -> dict:
    return {
        "name": name,
        "nodes": [
            {
                "parameters": {"httpMethod": "POST", "path": path, "responseMode": "lastNode", "options": {}},
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [0, 300],
                "webhookId": path.replace("/", "-"),
            },
            {
                "parameters": {"jsCode": "// synced by sync_workflow_code.py"},
                "name": node_label,
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [280, 300],
            },
        ],
        "connections": {
            "Webhook": {"main": [[{"node": node_label, "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "tags": [{"name": "renofacile-fr"}, {"name": "sofia"}],
    }


def main() -> None:
    for fname, wname, path, label in SPECS:
        target = WF / fname
        if target.is_file():
            print(f"  exists: {fname}")
            continue
        target.write_text(json.dumps(_wf(wname, path, label), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  created: {fname}")


if __name__ == "__main__":
    main()
