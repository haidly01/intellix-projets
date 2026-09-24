#!/usr/bin/env python3
"""Re-sync driven-b2b-qc workflows into n8n SQLite (safe publish)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WF = ROOT / "workflows"
DB = "/var/lib/docker/volumes/n8n_n8n_data/_data/database.sqlite"

WF_FILES = {
    "driven-b2b-qc — 01 Outbound": "01_outbound.json",
    "driven-b2b-qc — 02 Telephony Events": "02_telephony_events.json",
    "driven-b2b-qc — 03 Conversation Engine": "03_conversation_engine.json",
    "driven-b2b-qc — 04 Lead Chaud Driven": "04_qualified_lead.json",
    "driven-b2b-qc — 05 Lead Non Qualifié": "05_non_qualified_lead.json",
}


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "sync_workflow_code.py")], check=True)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT workflowId, projectId, role FROM shared_workflow WHERE workflowId='nYktiFeO2tPABvaQ'"
    )
    shared = cur.fetchone()
    project_id = shared[1] if shared else "cM7ARtZBoz5BmNiU"
    for wf_name, fname in WF_FILES.items():
        cur.execute("SELECT id FROM workflow_entity WHERE name=?", (wf_name,))
        row = cur.fetchone()
        if not row:
            print("missing", wf_name, file=sys.stderr)
            continue
        wf_id = row[0]
        data = json.loads((WF / fname).read_text(encoding="utf-8"))
        nodes = json.dumps(data["nodes"], ensure_ascii=False)
        conns = json.dumps(data.get("connections") or {}, ensure_ascii=False)
        settings = json.dumps(data.get("settings") or {"executionOrder": "v1"})
        ver = str(uuid.uuid4())
        cur.execute("DELETE FROM workflow_history WHERE workflowId=?", (wf_id,))
        cur.execute("DELETE FROM workflow_published_version WHERE workflowId=?", (wf_id,))
        cur.execute(
            """
            INSERT INTO workflow_history (versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, autosaved, nodeGroups)
            VALUES (?, ?, 'import', datetime('now'), datetime('now'), ?, ?, 0, '[]')
            """,
            (ver, wf_id, nodes, conns),
        )
        cur.execute(
            """
            INSERT INTO workflow_published_version (workflowId, publishedVersionId, createdAt, updatedAt)
            VALUES (?, ?, datetime('now'), datetime('now'))
            """,
            (wf_id, ver),
        )
        cur.execute(
            """
            UPDATE workflow_entity SET nodes=?, connections=?, settings=?, versionId=?, activeVersionId=?, active=1
            WHERE id=?
            """,
            (nodes, conns, settings, ver, ver, wf_id),
        )
        cur.execute("SELECT 1 FROM shared_workflow WHERE workflowId=?", (wf_id,))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO shared_workflow (workflowId, projectId, role, createdAt, updatedAt)
                VALUES (?, ?, 'workflow:owner', datetime('now'), datetime('now'))
                """,
                (wf_id, project_id),
            )
        for node in data.get("nodes", []):
            if node.get("type") == "n8n-nodes-base.webhook":
                path = node["parameters"]["path"]
                cur.execute("DELETE FROM webhook_entity WHERE webhookPath=?", (path,))
                cur.execute(
                    """
                    INSERT INTO webhook_entity (workflowId, webhookPath, method, node, webhookId, pathLength)
                    VALUES (?, ?, 'POST', 'Webhook', ?, NULL)
                    """,
                    (wf_id, path, node.get("webhookId")),
                )
        print("published", wf_name)
    conn.commit()
    conn.close()
    subprocess.run(["docker", "restart", "n8n"], check=True)
    print("n8n restarted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
