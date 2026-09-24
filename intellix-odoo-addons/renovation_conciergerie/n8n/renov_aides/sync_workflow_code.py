#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injecte le code JS des fichiers lib/ dans les workflows JSON."""
from __future__ import annotations

import json
from pathlib import Path

RENOV_DIR = Path(__file__).resolve().parent
LIB = RENOV_DIR / "lib"
WORKFLOWS = RENOV_DIR / "workflows"

def _load_js(*names: str) -> str:
    parts = [(LIB / n).read_text(encoding="utf-8").strip() for n in names]
    return "\n\n".join(parts)


INJECTIONS = {
    "03_conversation_engine.json": {
        "Sofía Engine": ("sofia_intent_keywords.js", "conversation_sofia_process.js"),
        "Write Google Sheet": "conversation_sheet_write.js",
    },
    "adapter_twilio.json": {
        "Normalize + TwiML ouverture": "adapter_sofia_start.js",
        "Normalize Recording": "adapter_normalize_recording.js",
        "Engine + TwiML réponse": "adapter_twiml_response.js",
    },
    "05_google_sheets_writer.json": {
        "Append Row": "sheets_writer.js",
    },
}


def main() -> None:
    for wf_name, nodes in INJECTIONS.items():
        path = WORKFLOWS / wf_name
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
    print("Workflow code synced.")


if __name__ == "__main__":
    main()
