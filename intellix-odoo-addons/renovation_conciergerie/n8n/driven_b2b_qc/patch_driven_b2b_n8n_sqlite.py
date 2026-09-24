#!/usr/bin/env python3
"""Patch driven-b2b-qc workflows in n8n SQLite (API token stale)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import uuid
import secrets
from pathlib import Path

ROOT = Path("/odoo/custom/addons/renovation_conciergerie/n8n/driven_b2b_qc")
WF = ROOT / "workflows"
DB_CONTAINER = "n8n"
DB_PATH = "/home/node/.n8n/database.sqlite"
LOCAL_DB = "/tmp/n8n_driven_patch.sqlite"

WF_MAP = {
    "driven-b2b-qc — 01 Outbound": "01_outbound.json",
    "driven-b2b-qc — 02 Telephony Events": "02_telephony_events.json",
    "driven-b2b-qc — 03 Conversation Engine": "03_conversation_engine.json",
    "driven-b2b-qc — 04 Lead Chaud Driven": "04_qualified_lead.json",
    "driven-b2b-qc — 05 Lead Non Qualifié": "05_non_qualified_lead.json",
    "driven-b2b-qc — 06 Stats Quotidiennes": "06_daily_stats.json",
}


def _new_id() -> str:
    return secrets.token_urlsafe(12)[:16]


def _ensure_workflows(cur, conn) -> None:
    """Insert minimal workflow rows if missing (fresh n8n DB)."""
    for wf_name in WF_MAP:
        cur.execute("SELECT id FROM workflow_entity WHERE name = ?", (wf_name,))
        if cur.fetchone():
            continue
        wf_id = _new_id()
        ver = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO workflow_entity (
                id, name, active, nodes, connections, settings,
                versionId, triggerCount, createdAt, updatedAt,
                isArchived, versionCounter, activeVersionId
            ) VALUES (?, ?, 1, '[]', '{}', '{"executionOrder":"v1"}',
                      ?, 0, datetime('now'), datetime('now'), 0, 1, ?)
            """,
            (wf_id, wf_name, ver, ver),
        )
        print(f"inserted workflow row: {wf_name} (id={wf_id})")
    conn.commit()


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "sync_workflow_code.py")], check=True)
    subprocess.run(["docker", "cp", f"{DB_CONTAINER}:{DB_PATH}", LOCAL_DB], check=True)
    conn = sqlite3.connect(LOCAL_DB)
    cur = conn.cursor()
    _ensure_workflows(cur, conn)
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
               SET nodes = ?, connections = ?, settings = ?, active = 1, updatedAt = datetime('now')
             WHERE name = ?
            """,
            (nodes_json, connections_json, settings_json, wf_name),
        )
        if cur.rowcount:
            patched += 1
            print(f"patched: {wf_name}")
        else:
            print(f"NOT FOUND: {wf_name}", file=sys.stderr)
    conn.commit()
    conn.close()
    subprocess.run(["docker", "cp", LOCAL_DB, f"{DB_CONTAINER}:{DB_PATH}"], check=True)
    subprocess.run(["docker", "restart", DB_CONTAINER], check=True)
    print(f"Done — {patched} workflows patched, n8n restarted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
