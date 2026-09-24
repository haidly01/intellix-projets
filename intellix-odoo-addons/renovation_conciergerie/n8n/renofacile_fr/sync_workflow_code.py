#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injecte le code JS dans les workflows RénoFacile FR."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "lib"
WF = ROOT / "workflows"

INJECTIONS = {
    "01_outbound.json": {"Outbound Dial": "outbound.js"},
    "02_telephony_events.json": {"Telephony Events": "telephony_events.js"},
    "03_conversation_engine.json": {"RénoFacile Engine": "conversation_engine.js"},
}


def main() -> None:
    for wf_name, nodes in INJECTIONS.items():
        path = WF / wf_name
        if not path.is_file():
            print(f"  skip missing {wf_name}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            spec = nodes.get(node.get("name", ""))
            if not spec:
                continue
            code = (LIB / spec).read_text(encoding="utf-8").strip()
            node.setdefault("parameters", {})["jsCode"] = code
            print(f"  {wf_name} ← {spec}")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("RénoFacile FR workflow code synced.")


if __name__ == "__main__":
    main()
