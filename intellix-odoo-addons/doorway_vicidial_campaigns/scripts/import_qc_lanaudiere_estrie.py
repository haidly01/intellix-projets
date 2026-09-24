#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import listes Lanaudière + Estrie → campagne VICIdial DW_QCB2C (Québec B2C).

Usage (sur le VPS) :
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf \\
    -d intellixcrm --no-http < /odoo/custom/addons/doorway_vicidial_campaigns/scripts/import_qc_lanaudiere_estrie.py

Fichiers attendus :
  /home/odoo/imports/lanaudiere.csv
  /home/odoo/imports/estrie.csv
"""
from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

CAMPAIGN_ID = "DW_QCB2C"
VICIDIAL_USER = "younessmarzguioui"
IMPORTS = (
    {
        "path": Path("/home/odoo/imports/lanaudiere.csv"),
        "list_name": "LANAUDIERE_QC",
        "description": "B2C Rénovation Lanaudière",
        "source_id": "LANAUDIERE",
    },
    {
        "path": Path("/home/odoo/imports/estrie.csv"),
        "list_name": "ESTRIE_QC",
        "description": "B2C Rénovation Estrie",
        "source_id": "ESTRIE",
    },
)

INSERT_SQL = """
INSERT INTO vicidial_list (
    entry_date, status, list_id, phone_code, phone_number,
    first_name, last_name, email, address1, city, state,
    province, postal_code, country_code, comments, `rank`,
    vendor_lead_code, source_id, called_count
) VALUES (
    NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s
)
"""


def _split_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split(None, 1)
    if len(parts) == 2:
        return parts[0][:30], parts[1][:30]
    return "", (parts[0] if parts else "")[:30]


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits[:10] if len(digits) >= 10 else ""


def _parse_csv(path: Path, source_id: str) -> list[dict]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    seen = set()
    for row in reader:
        phone = _normalize_phone(row.get("Phone") or "")
        if not phone or phone in seen:
            continue
        seen.add(phone)
        first, last = _split_name(row.get("Name") or "")
        rank = 0
        rank_raw = (row.get("Customer Rank") or "").strip()
        if rank_raw.isdigit():
            rank = int(rank_raw)
        rows.append(
            {
                "phone_number": phone,
                "first_name": first,
                "last_name": last,
                "email": "",
                "address1": (row.get("Street") or "").strip()[:100],
                "city": "",
                "state": "QC",
                "province": "QC",
                "postal_code": "",
                "country_code": "CA",
                "comments": (row.get("Notes") or "").strip()[:255],
                "rank": rank,
                "status": "NEW",
                "vendor_lead_code": source_id[:20],
                "source_id": source_id[:50],
                "phone_code": "1",
                "called_count": 0,
            }
        )
    return rows


def _bulk_insert(svc, list_id: str, contacts: list[dict], batch_size: int = 2000) -> tuple[int, int]:
    conn = svc._connect()
    ok, errors = 0, 0
    try:
        cur = conn.cursor()
        batch = []
        for row in contacts:
            batch.append(
                (
                    (row.get("status") or "NEW")[:6],
                    list_id,
                    row.get("phone_code") or "1",
                    row.get("phone_number", ""),
                    (row.get("first_name") or "")[:30],
                    (row.get("last_name") or "")[:30],
                    (row.get("email") or "")[:70],
                    (row.get("address1") or "")[:100],
                    (row.get("city") or "")[:50],
                    (row.get("state") or "")[:2],
                    (row.get("state") or row.get("province") or "")[:50],
                    (row.get("postal_code") or "")[:10],
                    (row.get("country_code") or "")[:3],
                    (row.get("comments") or "")[:255],
                    int(row.get("rank") or 0),
                    (row.get("vendor_lead_code") or "")[:20],
                    (row.get("source_id") or "ODOO")[:50],
                    int(row.get("called_count") or 0),
                )
            )
            if len(batch) >= batch_size:
                try:
                    cur.executemany(INSERT_SQL, batch)
                    conn.commit()
                    ok += len(batch)
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("Batch insert error: %s", exc)
                    errors += len(batch)
                batch = []
        if batch:
            try:
                cur.executemany(INSERT_SQL, batch)
                conn.commit()
                ok += len(batch)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Final batch insert error: %s", exc)
                errors += len(batch)
        cur.close()
    finally:
        conn.close()
    return ok, errors


def _ensure_campaign_agent(svc, vicidial_user: str, campaign_id: str) -> None:
    conn = svc._connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM vicidial_campaign_agents
            WHERE user = %s AND campaign_id = %s LIMIT 1
            """,
            (vicidial_user[:20], campaign_id[:20]),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO vicidial_campaign_agents (
                    user, campaign_id, campaign_rank, campaign_weight, campaign_grade
                ) VALUES (%s, %s, 1, 10, 1)
                """,
                (vicidial_user[:20], campaign_id[:20]),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def run(env):
    from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
        VicidialService,
    )

    svc = VicidialService(env)
    if not svc.is_available():
        raise RuntimeError("MySQL VICIdial indisponible")

    Campaign = env["doorway.campaign"].sudo()
    Agent = env["doorway.campaign.agent.user"].sudo()
    camp = Campaign.search([("vicidial_campaign_id", "=", CAMPAIGN_ID)], limit=1)
    if not camp:
        raise RuntimeError("Campagne Odoo DW_QCB2C introuvable")

    agent = Agent.search([("vicidial_user", "=", VICIDIAL_USER)], limit=1)
    if not agent:
        raise RuntimeError("Agent VICIdial %s introuvable dans Odoo" % VICIDIAL_USER)

    results = []
    primary_list_id = None

    conn = svc._connect()
    try:
        cur = conn.cursor()
        for spec in IMPORTS:
            path = spec["path"]
            if not path.is_file():
                raise FileNotFoundError("Fichier manquant : %s" % path)
            list_id = svc._ensure_list(
                cur,
                CAMPAIGN_ID,
                spec["description"],
                list_name=spec["list_name"],
            )
            conn.commit()
            if not primary_list_id:
                primary_list_id = list_id
            contacts = _parse_csv(path, spec["source_id"])
            ok, errors = _bulk_insert(svc, list_id, contacts)
            results.append(
                {
                    "list_name": spec["list_name"],
                    "list_id": list_id,
                    "file": str(path),
                    "parsed": len(contacts),
                    "inserted": ok,
                    "errors": errors,
                }
            )
            print(
                "✓ %s (list_id=%s) : %s contacts, %s insérés, %s erreurs"
                % (spec["list_name"], list_id, len(contacts), ok, errors)
            )
        cur.execute(
            "UPDATE servers SET rebuild_conf_files='Y' WHERE generate_vicidial_conf='Y'"
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    _ensure_campaign_agent(svc, VICIDIAL_USER, CAMPAIGN_ID)

    camp.write(
        {
            "campaign_mode": "human_agent",
            "human_agent_ids": [(4, agent.id)],
            "vicidial_list_id": primary_list_id,
            "state": "ready",
            "description": (
                "B2C Rénovation Québec — listes LANAUDIERE_QC + ESTRIE_QC, "
                "trunk Door_App0, DID 15142251425"
            ),
        }
    )
    env.cr.commit()

    print("✓ Youness assigné à %s (mode human_agent)" % camp.name)
    print("✓ vicidial_campaign_agents : %s → %s" % (VICIDIAL_USER, CAMPAIGN_ID))
    return results


if __name__ == "__main__" or "env" in dir():
    try:
        run(env)  # noqa: F821 — fourni par odoo shell
    except NameError:
        print("Exécuter via odoo shell (voir en-tête du script).")
