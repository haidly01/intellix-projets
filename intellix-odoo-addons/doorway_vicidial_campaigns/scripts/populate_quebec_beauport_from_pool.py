#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remplit extraction « Québec » + liste VICIdial depuis pool B2C (FSAs Beauport 50 km)."""
from __future__ import annotations

import re

EXTRACTION_NAME = "Québec"
CAMPAIGN_ID = "DW_QCB2C"
LIST_NAME = "Québec"
RAYON_KM = 50

FSAS = set(
    "G1A G1B G1C G1E G1G G1H G1J G1K G1L G1M G1N G1P G1R G1S G1T G1V G1W G1X G1Y "
    "G2A G2B G2C G2E G2G G2J G2K G2L G2M G2N G3A G3B G3C G3E G3G G3J G3K G0A G0R".split()
)
POSTAL_RE = re.compile(r"\b(G[0-9][A-Z])\s?([0-9][A-Z][0-9])\b", re.I)

INSERT_SQL = """
INSERT INTO vicidial_list (
    entry_date, status, list_id, phone_code, phone_number,
    first_name, last_name, email, address1, city, state,
    province, postal_code, country_code, comments, `rank`,
    vendor_lead_code, source_id, called_count, gmt_offset_now
) VALUES (
    NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def _fsa(row) -> str:
    pc = (row.get("postal_code") or "").upper().replace(" ", "")
    if not pc:
        m = POSTAL_RE.search(row.get("address1") or "")
        if m:
            pc = (m.group(1) + m.group(2)).upper()
    return pc[:3] if len(pc) >= 3 else ""


def _fetch_pool(svc) -> list[dict]:
    conn = svc._connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT phone_number, first_name, last_name, email, address1, city,
                   postal_code, province, comments, vendor_lead_code, source_id
            FROM vicidial_list
            WHERE list_id IN (1007, 1009, 1010)
              AND phone_number REGEXP '^[2-9][0-9]{9}$'
            """
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    out, seen = [], set()
    for r in rows:
        if _fsa(r) not in FSAS:
            continue
        ph = _normalize_phone(r.get("phone_number"))
        if not ph or ph in seen:
            continue
        seen.add(ph)
        out.append(
            {
                "phone_number": ph,
                "first_name": (r.get("first_name") or "")[:30],
                "last_name": (r.get("last_name") or "")[:30],
                "email": (r.get("email") or "")[:70],
                "address1": (r.get("address1") or "")[:100],
                "city": (r.get("city") or "")[:50],
                "state": "QC",
                "province": "QC",
                "postal_code": (r.get("postal_code") or _fsa(r))[:10],
                "country_code": "CA",
                "comments": ("Québec %skm Beauport — %s" % (RAYON_KM, (r.get("comments") or "")[:200]))[:255],
                "status": "NEW",
                "phone_code": "1",
                "source_id": "QUEBEC_EXTRACT",
                "vendor_lead_code": "QUEBEC",
                "called_count": 0,
            }
        )
    return out


def _bulk_insert(svc, list_id: str, contacts: list[dict]) -> tuple[int, int]:
    conn = svc._connect()
    ok = errors = 0
    try:
        cur = conn.cursor()
        for row in contacts:
            try:
                cur.execute(
                    INSERT_SQL,
                    (
                        row["status"],
                        list_id,
                        row["phone_code"],
                        row["phone_number"],
                        row["first_name"],
                        row["last_name"],
                        row["email"],
                        row["address1"],
                        row["city"],
                        row["state"],
                        row["province"],
                        row["postal_code"],
                        row["country_code"],
                        row["comments"],
                        0,
                        row["vendor_lead_code"],
                        row["source_id"],
                        0,
                        -4.00,
                    ),
                )
                ok += 1
            except Exception:
                errors += 1
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return ok, errors


def run(env):
    from odoo import fields
    from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
        VicidialService,
    )

    Campagne = env["doorway.campagne.extraction"].sudo()
    Leads = env["doorway.leads.bruts"].sudo()
    svc = VicidialService(env)

    campagne = Campagne.search([("name", "=", EXTRACTION_NAME)], limit=1)
    if not campagne:
        raise RuntimeError("Extraction « %s » introuvable — lancer create_quebec_beauport_extraction.py d'abord")

    pool = _fetch_pool(svc)
    if not pool:
        raise RuntimeError("Aucun lead B2C dans la zone Beauport 50 km")

    existing = {l.dedup_key for l in Leads.search([("dedup_key", "!=", False)]) if l.dedup_key}
    created = 0
    for row in pool:
        key = row["phone_number"]
        if key in existing:
            continue
        name = (" ".join(filter(None, [row["first_name"], row["last_name"]])) or "Contact QC").strip()
        Leads.create(
            {
                "name": name[:128],
                "phone": row["phone_number"],
                "email": row["email"],
                "address": row["address1"],
                "city": row["city"],
                "campagne_id": campagne.id,
                "dedup_key": key,
                "source_key": "quebec_beauport_pool",
                "state": "brut",
            }
        )
        existing.add(key)
        created += 1

    campagne.write(
        {
            "state": "done",
            "progress_pct": 100.0,
            "date_end": fields.Datetime.now(),
            "leads_scraped_raw": len(pool),
            "result_summary": "%s leads zone Beauport %s km (pool B2C — scrapers CA bloqués VPS)"
            % (len(pool), RAYON_KM),
        }
    )

    conn = svc._connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT list_id FROM vicidial_lists WHERE campaign_id=%s AND list_name=%s LIMIT 1",
            (CAMPAIGN_ID, LIST_NAME[:30]),
        )
        row = cur.fetchone()
        list_id = str(row[0]) if row else svc._ensure_list(
            cur, CAMPAIGN_ID, "Québec Beauport %skm" % RAYON_KM, list_name=LIST_NAME
        )
        cur.execute("SELECT phone_number FROM vicidial_list WHERE list_id=%s", (list_id,))
        existing_phones = {r[0] for r in cur.fetchall()}
        conn.commit()
        cur.close()
    finally:
        conn.close()

    to_insert = [c for c in pool if c["phone_number"] not in existing_phones]
    ok, errors = _bulk_insert(svc, list_id, to_insert)

    env.cr.commit()
    print(
        "Extraction id=%s +%s leads Odoo | Liste %s (id=%s) +%s insérés (%s dup ignorés, %s err)"
        % (campagne.id, created, LIST_NAME, list_id, ok, len(pool) - len(to_insert), errors)
    )
    return {"list_id": list_id, "inserted": ok, "pool": len(pool)}


if __name__ == "__main__" or "env" in dir():
    run(env)  # noqa: F821
