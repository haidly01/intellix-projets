#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère les workflows n8n demo (clone Sofia ES — Abdallah)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
LIB = DEMO_DIR / "lib"
WORKFLOWS = DEMO_DIR / "workflows"
SRC_WF = Path("/odoo/custom/addons/renovation_conciergerie/n8n/sofia_es/workflows")
SRC_LIB = Path("/odoo/custom/addons/renovation_conciergerie/n8n/sofia_es/lib")
RENOV_LIB = Path("/odoo/custom/addons/renovation_conciergerie/n8n/renov_aides/lib")

WEBHOOK_PREFIX = "sofia-es-demo"
TAG = "sofia-es-demo"

CLONE_MAP = {
    "01_outbound_vicidial.json": {
        "name": "sofia-es-demo — 01 Outbound VICIdial",
        "path": f"{WEBHOOK_PREFIX}/outbound",
        "webhook_id": "sofia-es-demo-outbound",
        "code_node": "Dial VICIdial TrustSIP",
        "code_file": "outbound_vicidial_demo.js",
    },
    "02_vicidial_events.json": {
        "name": "sofia-es-demo — 02 VICIdial Events",
        "path": f"{WEBHOOK_PREFIX}/vicidial/event",
        "webhook_id": "sofia-es-demo-vicidial-agi",
        "code_node": "Normalize + Engine + Odoo",
        "code_file": "vicidial_events_demo.js",
    },
    "03_conversation_engine.json": {
        "name": "sofia-es-demo — 03 Conversation Engine",
        "path": f"{WEBHOOK_PREFIX}/conversation",
        "webhook_id": "sofia-es-demo-conversation",
        "code_nodes": {
            "Sofía Engine": ("sofia_intent_keywords.js", "conversation_sofia_process.js"),
            "Write Google Sheet": "conversation_sheet_write_demo.js",
        },
    },
    "04_google_sheets.json": {
        "name": "sofia-es-demo — 04 Google Sheets",
        "path": f"{WEBHOOK_PREFIX}/sheets",
        "webhook_id": "sofia-es-demo-sheets",
        "code_node": "Append Leads Espagne",
        "code_file": "sheets_writer_demo.js",
    },
}


def _resolve_lib(name: str) -> Path:
    for base in (SRC_LIB, RENOV_LIB):
        path = base / name
        if path.is_file():
            return path
    raise FileNotFoundError(name)


def _load_js(*names: str) -> str:
    return "\n\n".join(_resolve_lib(n).read_text(encoding="utf-8").strip() for n in names)


def _patch_conversation_code(code: str) -> str:
    code = code.replace(
        "$env.CAMPAIGN_ID || 'sofia-test-maroc-juin2026'",
        "$env.DEMO_CAMPAIGN_ID || 'sofia-es-demo-abdallah'",
    )
    code = code.replace(
        "$env.GOOGLE_SHEETS_TAB || 'Leads_Sofia_Test'",
        "$env.GOOGLE_SHEETS_TAB_DEMO || 'Leads_Sofia_Demo_Abdallah'",
    )
    return code


def _clone_workflow(src_name: str, spec: dict) -> None:
    data = json.loads((SRC_WF / src_name).read_text(encoding="utf-8"))
    data["name"] = spec["name"]
    data["tags"] = [{"name": TAG}, {"name": "demo-abdallah"}, {"name": "vicidial"}]

    for node in data.get("nodes", []):
        node.pop("id", None)
        params = node.setdefault("parameters", {})
        if node.get("type") == "n8n-nodes-base.webhook":
            params["path"] = spec["path"]
            node["webhookId"] = spec["webhook_id"]

        if "code_nodes" in spec:
            js_spec = spec["code_nodes"].get(node.get("name", ""))
            if not js_spec:
                continue
            if isinstance(js_spec, tuple):
                code = _load_js(*js_spec)
                if node.get("name") == "Sofía Engine":
                    code = _patch_conversation_code(code)
            else:
                code = (LIB / js_spec).read_text(encoding="utf-8").strip()
            params["jsCode"] = code
        elif spec.get("code_node") == node.get("name") and spec.get("code_file"):
            params["jsCode"] = (LIB / spec["code_file"]).read_text(encoding="utf-8").strip()

    WORKFLOWS.mkdir(parents=True, exist_ok=True)
    dst = WORKFLOWS / src_name
    dst.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  {dst.name} ← {spec['name']}")


def main() -> None:
    for fname, spec in CLONE_MAP.items():
        _clone_workflow(fname, spec)
    print("Sofia ES demo workflows synced.")


if __name__ == "__main__":
    main()
