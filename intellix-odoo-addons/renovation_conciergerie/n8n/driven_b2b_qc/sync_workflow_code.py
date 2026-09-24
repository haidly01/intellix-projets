#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injecte le code JS dans les workflows Driven B2B QC."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "lib"
WF = ROOT / "workflows"

INJECTIONS = {
    "01_outbound.json": {"Outbound Dial": "outbound.js"},
    "02_telephony_events.json": {"Telephony Events": "telephony_events.js"},
    "03_conversation_engine.json": {
        "Alex Driven Engine": (
            "driven_b2b_config.js",
            "conversation_driven_process.js",
        ),
    },
    "04_qualified_lead.json": {"Qualified Lead": ("driven_b2b_config.js", "qualified_lead.js")},
    "05_non_qualified_lead.json": {"Non Qualified": "non_qualified_lead.js"},
    "06_daily_stats.json": {"Daily Stats": "daily_stats.js"},
}


def _load_js(*names: str) -> str:
    return "\n\n".join((LIB / n).read_text(encoding="utf-8").strip() for n in names)


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
            if isinstance(spec, tuple):
                code = _load_js(*spec)
                label = " + ".join(spec)
            else:
                code = (LIB / spec).read_text(encoding="utf-8").strip()
                label = spec
            node.setdefault("parameters", {})["jsCode"] = code
            print(f"  {wf_name} ← {label}")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Driven B2B QC workflow code synced.")


if __name__ == "__main__":
    main()
