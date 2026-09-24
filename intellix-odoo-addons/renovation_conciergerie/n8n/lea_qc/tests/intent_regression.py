#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests d'intention extraits de conversation_sofia_process.js (source unique)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib" / "conversation_sofia_process.js"
FIXTURES = Path(__file__).resolve().parent / "golden_transcripts.json"


def extract_function(src: str, name: str) -> str:
    start = src.index(f"function {name}")
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start : j + 1]
    raise ValueError(f"function {name} non fermée")


def load_engine():
    src = LIB.read_text(encoding="utf-8")
    norm_src = extract_function(src, "normTranscript")
    detect_src = extract_function(src, "detectIntent")
    ns: dict = {}
    exec(norm_src + "\n" + detect_src, ns)  # noqa: S102
    return ns["normTranscript"], ns["detectIntent"]


BUILTIN_TESTS = [
    {"step": "GREETING", "raw": "oui", "expect": {"intent": "proprietaire"}, "label": "greeting oui"},
    {"step": "GREETING", "raw": "ouais", "expect": {"intent": "proprietaire"}, "label": "greeting ouais"},
    {"step": "GREETING", "raw": "je veux vendre ma maison", "expect": {"intent": "proprietaire", "besoin": "immo"}, "label": "vendre ma maison"},
    {"step": "GREETING", "raw": "cuisine", "expect": {"intent": "proprietaire", "besoin": "reno"}, "label": "cuisine au greeting"},
    {"step": "GREETING", "raw": "sous-sol", "expect": {"intent": "proprietaire", "besoin": "reno"}, "label": "sous-sol au greeting"},
    {"step": "QUESTION_PROJET", "raw": "Sous sol", "expect": {"intent": "projet"}, "label": "sous-sol projet"},
    {"step": "QUESTION_PROJET", "raw": "cuisine et salle de bain", "expect": {"intent": "projet"}, "label": "cuisine sdb"},
    {"step": "QUESTION_PROJET", "raw": "sou sol", "expect": {"intent": "projet"}, "label": "sou sol"},
    {"step": "QUESTION_BESOIN", "raw": "vendre ma maison", "expect": {"intent": "immo"}, "label": "besoin immo"},
    {"step": "GREETING", "raw": "", "expect": {"intent": "silence"}, "label": "silence greeting"},
]


def js_regex_to_py(pattern: str) -> re.Pattern:
    """Convertit les patterns JS utilisés dans detectIntent (approximation suffisante pour les tests)."""
    return re.compile(pattern, re.IGNORECASE)


def main() -> int:
    norm_transcript, detect_intent = load_engine()
    fixture_tests: list = []
    if FIXTURES.is_file():
        fixture_tests = json.loads(FIXTURES.read_text(encoding="utf-8"))

    all_tests = BUILTIN_TESTS + fixture_tests
    passed = failed = 0

    for t in all_tests:
        text = norm_transcript(t["raw"])
        got = detect_intent(t["step"], text)
        expect = t.get("expect") or {"intent": t.get("expect_intent")}
        ok = got.get("intent") == expect.get("intent")
        if ok and "besoin" in expect:
            ok = got.get("besoin") == expect["besoin"]
        label = t.get("label") or f"[{t['step']}] \"{t['raw']}\""
        if ok:
            passed += 1
            print(f"OK  {label}")
        else:
            failed += 1
            extra = f" besoin={expect.get('besoin')}" if "besoin" in expect else ""
            got_extra = f" besoin={got.get('besoin')}" if got.get("besoin") else ""
            print(
                f"FAIL {label}: got intent={got.get('intent')}{got_extra}, "
                f"expected intent={expect.get('intent')}{extra}"
            )

    print(f"\n{passed}/{len(all_tests)} tests intent passés")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
