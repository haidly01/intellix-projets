#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crée les squelettes workflows Soumission QC si absents."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WF = ROOT / "workflows"
WF.mkdir(exist_ok=True)

SPECS = [
    ("01_outbound.json", "soumission-qc — 01 Outbound", "soumission-qc/outbound", "Outbound Dial"),
    ("02_telephony_events.json", "soumission-qc — 02 Telephony Events", "soumission-qc/event", "Telephony Events"),
    ("03_conversation_engine.json", "soumission-qc — 03 Conversation Engine", "soumission-qc/conversation", "Sofia QC Engine"),
    ("04_qualified_lead.json", "soumission-qc — 04 Lead Qualifié", "soumission-qc/qualified", "Qualified Lead"),
    ("05_non_qualified_lead.json", "soumission-qc — 05 Lead Non Qualifié", "soumission-qc/non-qualified", "Non Qualified"),
    ("06_daily_stats.json", "soumission-qc — 06 Stats Quotidiennes", "soumission-qc/stats", "Daily Stats"),
]


def _wf(name: str, path: str, node_label: str, cron: bool = False) -> dict:
    nodes = [
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
    ]
    if cron:
        nodes = [
            {
                "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 18 * * *"}]}},
                "name": "Cron 18h",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 300],
            },
            nodes[1],
        ]
    trigger = nodes[0]["name"]
    return {
        "name": name,
        "nodes": nodes,
        "connections": {trigger: {"main": [[{"node": node_label, "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
        "tags": [{"name": "soumission-qc"}, {"name": "sofia"}],
    }


def main() -> None:
    for fname, wname, path, label in SPECS:
        fp = WF / fname
        if fp.is_file():
            continue
        cron = fname.startswith("06_")
        fp.write_text(json.dumps(_wf(wname, path, label, cron=cron), indent=2) + "\n", encoding="utf-8")
        print(f"created {fname}")


if __name__ == "__main__":
    main()
