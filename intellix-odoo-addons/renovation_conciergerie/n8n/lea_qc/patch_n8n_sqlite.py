#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch atomique des workflows lea-qc dans n8n SQLite (API token stale)."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WF = ROOT / "workflows"
DB_CONTAINER = os.environ.get("N8N_CONTAINER", "n8n")
DB_PATH = "/home/node/.n8n/database.sqlite"

WF_MAP = {
    "lea-qc — 01 Outbound": "01_outbound.json",
    "lea-qc — 02 Telephony Events": "02_telephony_events.json",
    "lea-qc — 03 Conversation Engine": "03_conversation_engine.json",
    "lea-qc — 04 Lead Qualifié": "04_qualified_lead.json",
    "lea-qc — 05 Lead Non Qualifié": "05_non_qualified_lead.json",
    "lea-qc — 06 Stats Quotidiennes": "06_daily_stats.json",
}


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "sync_workflow_code.py")], check=True)

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        local_db = tmp.name

    try:
        subprocess.run(["docker", "cp", f"{DB_CONTAINER}:{DB_PATH}", local_db], check=True)
        conn = sqlite3.connect(local_db)
        cur = conn.cursor()
        patched = 0
        for wf_name, fname in WF_MAP.items():
            path = WF / fname
            if not path.is_file():
                print(f"skip missing {fname}")
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            nodes_json = json.dumps(data["nodes"], ensure_ascii=False)
            connections_json = json.dumps(data.get("connections") or {}, ensure_ascii=False)
            settings_json = json.dumps(data.get("settings") or {"executionOrder": "v1"})
            cur.execute(
                """
                UPDATE workflow_entity
                   SET nodes = ?, connections = ?, settings = ?, updatedAt = datetime('now')
                 WHERE name = ?
                """,
                (nodes_json, connections_json, settings_json, wf_name),
            )
            if cur.rowcount:
                patched += 1
                print(f"patched: {wf_name}")
                # n8n exécute workflow_history (activeVersionId), pas workflow_entity.nodes seul
                cur.execute(
                    "SELECT id, activeVersionId FROM workflow_entity WHERE name = ?",
                    (wf_name,),
                )
                row = cur.fetchone()
                if row and row[1]:
                    cur.execute(
                        """
                        UPDATE workflow_history
                           SET nodes = ?, connections = ?, updatedAt = datetime('now')
                         WHERE workflowId = ? AND versionId = ?
                        """,
                        (nodes_json, connections_json, row[0], row[1]),
                    )
                    if cur.rowcount:
                        print(f"  synced workflow_history {row[1][:8]}…")
                    else:
                        print(f"  WARN: workflow_history miss {row[1][:8]}…", file=sys.stderr)
            else:
                print(f"NOT FOUND: {wf_name}", file=sys.stderr)
        conn.commit()
        conn.close()
        subprocess.run(["docker", "cp", local_db, f"{DB_CONTAINER}:{DB_PATH}"], check=True)
        # docker cp preserves host root ownership — n8n (node) needs write access
        subprocess.run(
            ["docker", "exec", "-u", "root", DB_CONTAINER, "chown", "node:node", DB_PATH],
            check=False,
        )
        print(f"Done — {patched} workflows patched.")
        return 0 if patched == len(WF_MAP) else 1
    finally:
        Path(local_db).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
