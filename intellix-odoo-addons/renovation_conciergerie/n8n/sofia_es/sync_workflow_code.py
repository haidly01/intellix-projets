#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injecte le code JS dans les workflows Sofia Espagne."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

SOFIA_DIR = Path(__file__).resolve().parent
LIB = SOFIA_DIR / "lib"
RENOV_LIB = SOFIA_DIR.parent / "renov_aides" / "lib"
WORKFLOWS = SOFIA_DIR / "workflows"
RENOV_WF = SOFIA_DIR.parent / "renov_aides" / "workflows"


def _load_js(*names: str, base: Path = LIB) -> str:
    parts = [(base / n).read_text(encoding="utf-8").strip() for n in names]
    return "\n\n".join(parts)


def _ensure_conversation_workflow() -> None:
    src = RENOV_WF / "03_conversation_engine.json"
    dst = WORKFLOWS / "03_conversation_engine.json"
    if not src.is_file():
        return
    data = json.loads(src.read_text(encoding="utf-8"))
    data["name"] = "sofia-es — 03 Conversation Engine"
    for node in data.get("nodes", []):
        params = node.get("parameters") or {}
        if params.get("path") == "renov/conversation":
            params["path"] = "sofia-es/conversation"
            node["webhookId"] = "sofia-es-conversation"
    tags = data.get("tags") or []
    if not any(t.get("name") == "sofia-es" for t in tags):
        tags.append({"name": "sofia-es"})
    data["tags"] = tags
    dst.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_renov_libs() -> None:
    for name in ("sofia_intent_keywords.js", "conversation_sofia_process.js"):
        src = RENOV_LIB / name
        if src.is_file():
            shutil.copy2(src, LIB / name)


INJECTIONS = {
    "01_outbound_vicidial.json": {
        "Dial VICIdial TrustSIP": "outbound_vicidial.js",
    },
    "02_vicidial_events.json": {
        "Normalize + Engine + Odoo": "vicidial_events.js",
    },
    "03_conversation_engine.json": {
        "Sofía Engine": ("sofia_intent_keywords.js", "conversation_sofia_process.js"),
        "Write Google Sheet": "conversation_sheet_write.js",
    },
    "04_google_sheets.json": {
        "Append Leads Espagne": "sheets_writer_es.js",
    },
}


def main() -> None:
    _copy_renov_libs()
    _ensure_conversation_workflow()
    for wf_name, nodes in INJECTIONS.items():
        path = WORKFLOWS / wf_name
        if not path.is_file():
            print(f"  skip missing {wf_name}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            js_spec = nodes.get(node.get("name", ""))
            if not js_spec:
                continue
            if isinstance(js_spec, tuple):
                code = _load_js(*js_spec)
                label = " + ".join(js_spec)
            else:
                code = (LIB / js_spec).read_text(encoding="utf-8").strip()
                label = js_spec
            node.setdefault("parameters", {})["jsCode"] = code
            print(f"  {wf_name} ← {label} ({node['name']})")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Sofia ES workflow code synced.")


if __name__ == "__main__":
    main()
