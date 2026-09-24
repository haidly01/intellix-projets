#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extraction Odoo « Québec » (50 km Beauport) + liste VICIdial « Québec » sur DW_QCB2C.

Usage:
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf \\
    -d intellixcrm --no-http < /odoo/custom/addons/doorway_vicidial_campaigns/scripts/create_quebec_beauport_extraction.py
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime

_logger = logging.getLogger(__name__)

EXTRACTION_NAME = "Québec"
CAMPAIGN_ID = "DW_QCB2C"
LIST_NAME = "Québec"
MOT_CLE = "rénovation maison"
VILLE_REGION = "Beauport, QC, Canada"
RAYON_KM = 50
VOLUME_CIBLE = 150
BEAUPORT_LAT = 46.8906
BEAUPORT_LNG = -71.1824

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


def _haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _geocode_city(city: str) -> tuple[float, float] | None:
    """Approximation légère pour filtrer hors rayon (villes connues RCM Québec)."""
    if not city:
        return None
    c = city.lower().strip()
    known = {
        "beauport": (46.8906, -71.1824),
        "québec": (46.8139, -71.2080),
        "quebec": (46.8139, -71.2080),
        "lévis": (46.7381, -71.1731),
        "levis": (46.7381, -71.1731),
        "l'ancienne-lorette": (46.7939, -71.3529),
        "ancienne-lorette": (46.7939, -71.3529),
        "sainte-foy": (46.7710, -71.2890),
        "charlesbourg": (46.8667, -71.2667),
        "boischatel": (46.8989, -71.1508),
        "montmagny": (46.9734, -70.5549),
        "saint-raymond": (46.8894, -71.8358),
        "thetford mines": (46.0937, -71.3054),
        "saint-georges": (46.1132, -70.6653),
    }
    for key, coords in known.items():
        if key in c:
            return coords
    return None


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "23456789":
        return digits
    return ""


def _split_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split(None, 1)
    if len(parts) == 2:
        return parts[0][:30], parts[1][:30]
    return "", (parts[0] if parts else "")[:30]


def _bulk_insert(svc, list_id: str, contacts: list[dict]) -> tuple[int, int]:
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
                    (row.get("state") or "QC")[:2],
                    (row.get("province") or "QC")[:50],
                    (row.get("postal_code") or "")[:10],
                    (row.get("country_code") or "CA")[:3],
                    (row.get("comments") or "")[:255],
                    int(row.get("rank") or 0),
                    (row.get("vendor_lead_code") or "QUEBEC")[:20],
                    (row.get("source_id") or "ODOO")[:50],
                    int(row.get("called_count") or 0),
                    -4.00,
                )
            )
            if len(batch) >= 500:
                try:
                    cur.executemany(INSERT_SQL, batch)
                    conn.commit()
                    ok += len(batch)
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("batch error: %s", exc)
                    errors += len(batch)
                batch = []
        if batch:
            try:
                cur.executemany(INSERT_SQL, batch)
                conn.commit()
                ok += len(batch)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("final batch error: %s", exc)
                errors += len(batch)
        cur.close()
    finally:
        conn.close()
    return ok, errors


def _run_extraction(env):
    from odoo import fields

    Campagne = env["doorway.campagne.extraction"].sudo()
    Source = env["doorway.source.registry"].sudo()

    campagne = Campagne.search([("name", "=", EXTRACTION_NAME)], limit=1)
    if campagne and campagne.state == "done" and campagne.leads_count:
        print("Extraction existante : id=%s leads=%s" % (campagne.id, campagne.leads_count))
        return campagne

    sources = Source.search([("pays", "=", "canada"), ("actif", "=", True)])
    if not sources:
        raise RuntimeError("Aucune source Canada active")

    if campagne:
        if campagne.state not in ("draft", "error"):
            campagne.write({"state": "draft"})
    else:
        campagne = Campagne.create(
            {
                "name": EXTRACTION_NAME,
                "mot_cle": MOT_CLE,
                "zone_geographique": "canada",
                "ville_region": VILLE_REGION,
                "rayon_km": RAYON_KM,
                "volume_cible": VOLUME_CIBLE,
                "sources_selectionnees": [(6, 0, sources.ids)],
                "marge_pct": 0.0,
            }
        )

    campagne.action_calculer_cout()
    campagne.write(
        {
            "state": "running",
            "progress_pct": 0.0,
            "date_start": fields.Datetime.now(),
            "error_message": False,
            "leads_skipped_dup": 0,
            "leads_scraped_raw": 0,
        }
    )
    env.cr.commit()
    print("Extraction lancée id=%s (rayon %s km, %s)…" % (campagne.id, RAYON_KM, VILLE_REGION))
    campagne._execute_extraction()
    env.cr.commit()
    campagne.invalidate_recordset()
    print(
        "Extraction terminée : %s leads (bruts scrapés %s, doublons %s)"
        % (campagne.leads_count, campagne.leads_skipped_dup, campagne.leads_scraped_raw)
    )
    return campagne


def _leads_to_vicidial(env, campagne):
    from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
        VicidialService,
    )

    svc = VicidialService(env)
    if not svc.is_available():
        raise RuntimeError("MySQL VICIdial indisponible")

    Leads = env["doorway.leads.bruts"].sudo()
    records = Leads.search(
        [("campagne_id", "=", campagne.id), ("phone", "!=", False)]
    )

    contacts = []
    seen = set()
    skipped_distance = 0
    for rec in records:
        phone = _normalize_phone(rec.phone)
        if not phone or phone in seen:
            continue
        city = (rec.city or rec.region or "").strip()
        coords = _geocode_city(city)
        if coords:
            dist = _haversine_km(BEAUPORT_LAT, BEAUPORT_LNG, coords[0], coords[1])
            if dist > RAYON_KM:
                skipped_distance += 1
                continue
        seen.add(phone)
        first, last = _split_name(rec.name)
        contacts.append(
            {
                "phone_number": phone,
                "first_name": first,
                "last_name": last,
                "email": (rec.email or "")[:70],
                "address1": (rec.address or "")[:100],
                "city": city[:50],
                "state": "QC",
                "province": "QC",
                "country_code": "CA",
                "comments": ("Extraction %s — %s km Beauport" % (EXTRACTION_NAME, RAYON_KM))[:255],
                "status": "NEW",
                "phone_code": "1",
                "source_id": (rec.source_key or "QUEBEC_EXTRACT")[:50],
                "vendor_lead_code": "QUEBEC",
                "called_count": 0,
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
        if row:
            list_id = str(row[0])
        else:
            list_id = svc._ensure_list(
                cur,
                CAMPAIGN_ID,
                "B2C Québec Beauport %skm" % RAYON_KM,
                list_name=LIST_NAME,
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    ok, errors = _bulk_insert(svc, list_id, contacts)
    print(
        "Liste VICIdial « %s » (list_id=%s) : %s insérés, %s erreurs, "
        "%s hors rayon ignorés, %s avec téléphone"
        % (LIST_NAME, list_id, ok, errors, skipped_distance, len(contacts))
    )
    return {"list_id": list_id, "inserted": ok, "errors": errors, "contacts": len(contacts)}


def run(env):
    campagne = _run_extraction(env)
    result = _leads_to_vicidial(env, campagne)
    env.cr.commit()
    print("✓ Terminé @ %s" % datetime.now().isoformat(timespec="seconds"))
    return {"campagne_id": campagne.id, "leads_count": campagne.leads_count, **result}


if __name__ == "__main__" or "env" in dir():
    try:
        run(env)  # noqa: F821
    except NameError:
        print("Exécuter via odoo shell (voir en-tête du script).")
