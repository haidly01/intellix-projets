#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import listes QC (Lanaudière, Rive Sud, Montréal) → DW_QCB2C avec dédup globale.

Usage standalone (VPS) :
  python3 import_pending_lists.py --region lanaudiere --limit 1000
  python3 import_pending_lists.py --region rive_sud
  python3 import_pending_lists.py --region montreal
  python3 import_pending_lists.py --region all

Usage Odoo shell :
  IMPORT_REGION=lanaudiere IMPORT_LIMIT=1000 sudo -u odoo python3 .../odoo-bin shell \\
    -c /etc/odoo-server.conf -d intellixcrm --no-http \\
    < .../import_pending_lists.py
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

CAMPAIGN_ID = "DW_QCB2C"
LISTES_BASE = Path("/opt/intellix-mcp/data/Listes/Listes")

REGIONS = {
    "lanaudiere": {
        "globs": ["Lanaudi*/*.xlsx"],
        "list_name": "LANAUDIERE_QC",
        "description": "B2C Rénovation Lanaudière",
        "source_id": "LANAUDIERE",
    },
    "rive_sud": {
        "globs": ["Rive Sud/*.xlsx", "Copy*Rive*.xlsx"],
        "list_name": "RIVE_SUD_QC",
        "description": "B2C Rénovation Rive Sud",
        "source_id": "RIVE_SUD",
    },
    "montreal": {
        "globs": ["Montr*/M*.xlsx"],
        "list_name": "MONTREAL_QC",
        "description": "B2C Rénovation Montréal",
        "source_id": "MONTREAL",
    },
}

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

PHONE_RE = re.compile(r"^[2-9][0-9]{9}$")


def _normalize_phone(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, float):
        raw = int(raw)
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if PHONE_RE.match(digits) else ""


def _cell_str(val, max_len: int = 0) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if isinstance(val, float) and val == int(val):
        s = str(int(val))
    if max_len:
        return s[:max_len]
    return s


def _build_comments(row: dict) -> str:
    parts = []
    for key in ("Income", "Home Ownership", "Language", "Household Size", "Dwelling Age", "Dwelling Type"):
        val = _cell_str(row.get(key))
        if val:
            parts.append("%s: %s" % (key, val))
    addr2 = _cell_str(row.get("Address 2"))
    if addr2:
        parts.append("Addr2: %s" % addr2)
    return " | ".join(parts)[:255]


def _resolve_files(region_key: str) -> list[Path]:
    spec = REGIONS[region_key]
    found: list[Path] = []
    seen = set()
    for pattern in spec["globs"]:
        for p in sorted(glob.glob(str(LISTES_BASE / pattern))):
            path = Path(p)
            if path.is_file() and path.suffix.lower() == ".xlsx":
                key = str(path.resolve())
                if key not in seen:
                    seen.add(key)
                    found.append(path)
    return found


def _parse_xlsx(path: Path, source_id: str, existing_phones: set[str], file_seen: set[str], limit: int | None):
    import openpyxl

    stats = {
        "file": str(path),
        "rows_read": 0,
        "no_phone": 0,
        "invalid_phone": 0,
        "dup_file": 0,
        "dup_global": 0,
        "parsed": 0,
    }
    contacts = []

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = None
    col = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [_cell_str(h) for h in row]
            col = {h: idx for idx, h in enumerate(headers) if h}
            continue
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        stats["rows_read"] += 1

        def get(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx]

        phone = _normalize_phone(get("Phone"))
        if not phone:
            raw = get("Phone")
            if raw is None or str(raw).strip() == "":
                stats["no_phone"] += 1
            else:
                stats["invalid_phone"] += 1
            continue
        if phone in file_seen:
            stats["dup_file"] += 1
            continue
        file_seen.add(phone)
        if phone in existing_phones:
            stats["dup_global"] += 1
            continue

        first = _cell_str(get("First Name"), 30)
        last = _cell_str(get("Last Name"), 30)
        addr = _cell_str(get("Street Address"), 100)
        city = _cell_str(get("City"), 50)
        province = _cell_str(get("Province"), 2) or "QC"
        postcode = _cell_str(get("Postcode"), 10).upper().replace(" ", "")

        row_dict = {h: (row[col[h]] if h in col and col[h] < len(row) else "") for h in col}
        contacts.append(
            {
                "phone_number": phone,
                "first_name": first,
                "last_name": last,
                "email": "",
                "address1": addr,
                "city": city,
                "state": province[:2],
                "province": province[:50],
                "postal_code": postcode,
                "country_code": "CA",
                "comments": _build_comments(row_dict),
                "status": "NEW",
                "phone_code": "1",
                "source_id": source_id[:50],
                "vendor_lead_code": source_id[:20],
                "called_count": 0,
                "rank": 0,
                "gmt_offset_now": "-5",
            }
        )
        existing_phones.add(phone)
        stats["parsed"] += 1
        if limit and stats["parsed"] >= limit:
            break

    wb.close()
    return contacts, stats


def _load_existing_phones(conn) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT phone_number FROM vicidial_list WHERE phone_number REGEXP '^[2-9][0-9]{9}$'")
    phones = {row[0] for row in cur.fetchall()}
    cur.close()
    return phones


def _ensure_list(cur, campaign_id: str, list_name: str, description: str) -> str:
    cur.execute(
        """
        SELECT list_id FROM vicidial_lists
        WHERE campaign_id = %s AND list_name = %s LIMIT 1
        """,
        (campaign_id, list_name[:30]),
    )
    row = cur.fetchone()
    if row:
        return str(row[0])
    cur.execute("SELECT COALESCE(MAX(list_id), 100) + 1 FROM vicidial_lists")
    new_list_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO vicidial_lists (
            list_id, list_name, campaign_id, active, list_description
        ) VALUES (%s, %s, %s, 'Y', %s)
        """,
        (new_list_id, list_name[:30], campaign_id, ("Odoo — %s" % description)[:255]),
    )
    return str(new_list_id)


def _bulk_insert(conn, list_id: str, contacts: list[dict], batch_size: int = 2000) -> tuple[int, int]:
    ok, errors = 0, 0
    cur = conn.cursor()
    batch = []
    for row in contacts:
        batch.append(
            (
                row["status"][:6],
                int(list_id),
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
                row["rank"],
                row["vendor_lead_code"],
                row["source_id"],
                row["called_count"],
                row["gmt_offset_now"],
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
    return ok, errors


def _connect_mysql():
    try:
        import mysql.connector
    except ImportError:
        import pymysql

        return pymysql.connect(
            host="127.0.0.1",
            port=3307,
            user="vicidial",
            password=open("/etc/odoo-server.conf").read().split("VICIDIAL_DB_PASS = ")[1].split("\n")[0].strip()
            if "VICIDIAL_DB_PASS" in open("/etc/odoo-server.conf").read()
            else "",
            database="asterisk",
            charset="utf8mb4",
        )
    cnf = "/opt/intellix-mcp/mysql-vicidial.cnf"
    if os.path.isfile(cnf):
        return mysql.connector.connect(option_files=cnf, charset="utf8mb4")
    return mysql.connector.connect(
        host="127.0.0.1",
        port=3307,
        database="asterisk",
        charset="utf8mb4",
    )


def _reload_hopper(conn, campaign_id: str, hopper_level: int = 100) -> int:
    cur = conn.cursor()
    cur.execute("DELETE FROM vicidial_hopper WHERE campaign_id = %s", (campaign_id,))
    cur.execute(
        """
        INSERT INTO vicidial_hopper (
            lead_id, campaign_id, status, list_id,
            gmt_offset_now, state, alt_dial, priority
        )
        SELECT vl.lead_id, %s, 'READY', vl.list_id,
               vl.gmt_offset_now, vl.state, 'NONE', 0
        FROM vicidial_list vl
        INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
        WHERE vls.campaign_id = %s AND vls.active = 'Y'
          AND vl.status = 'NEW' AND vl.called_since_last_reset = 'N'
        ORDER BY vl.lead_id LIMIT %s
        """,
        (campaign_id, campaign_id, hopper_level),
    )
    cur.execute("SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id = %s", (campaign_id,))
    count = int(cur.fetchone()[0])
    cur.execute("UPDATE servers SET rebuild_conf_files='Y' WHERE generate_vicidial_conf='Y'")
    conn.commit()
    cur.close()
    return count


def _count_campaign_lists(conn, campaign_id: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cl.list_id, cl.list_name,
               (SELECT COUNT(*) FROM vicidial_list vl WHERE vl.list_id=cl.list_id) AS cnt
        FROM vicidial_lists cl
        WHERE cl.campaign_id = %s
        ORDER BY cl.list_id
        """,
        (campaign_id,),
    )
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM vicidial_list")
    total = int(cur.fetchone()[0])
    cur.close()
    return {"lists": rows, "total_vicidial_list": total}


def import_region(svc_or_conn, region_key: str, limit: int | None = None, dry_run: bool = False) -> dict:
    if region_key not in REGIONS:
        raise ValueError("Région inconnue : %s" % region_key)

    spec = REGIONS[region_key]
    files = _resolve_files(region_key)
    if not files:
        raise FileNotFoundError("Aucun fichier xlsx pour %s dans %s" % (region_key, LISTES_BASE))

    if hasattr(svc_or_conn, "_connect"):
        conn = svc_or_conn._connect()
        own_conn = False
    else:
        conn = svc_or_conn
        own_conn = False

    result = {
        "region": region_key,
        "list_name": spec["list_name"],
        "files": [],
        "inserted": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    try:
        existing_phones = _load_existing_phones(conn)
        result["existing_phones_before"] = len(existing_phones)

        cur = conn.cursor()
        list_id = _ensure_list(cur, CAMPAIGN_ID, spec["list_name"], spec["description"])
        if not dry_run:
            conn.commit()
        cur.close()
        result["list_id"] = list_id

        all_contacts = []
        for path in files:
            file_seen: set[str] = set()
            remaining = None
            if limit:
                remaining = max(0, limit - len(all_contacts))
                if remaining == 0:
                    break
            contacts, fstats = _parse_xlsx(
                path, spec["source_id"], existing_phones, file_seen, remaining
            )
            fstats["would_insert"] = len(contacts)
            result["files"].append(fstats)
            all_contacts.extend(contacts)
            print(
                "  %s : lu=%s parsés=%s dup_global=%s dup_fichier=%s sans_tel=%s invalides=%s"
                % (
                    path.name,
                    fstats["rows_read"],
                    fstats["parsed"],
                    fstats["dup_global"],
                    fstats["dup_file"],
                    fstats["no_phone"],
                    fstats["invalid_phone"],
                )
            )

        result["parsed_total"] = len(all_contacts)
        if dry_run:
            print("[DRY-RUN] %s contacts prêts pour list_id=%s" % (len(all_contacts), list_id))
            return result

        ok, errors = _bulk_insert(conn, list_id, all_contacts)
        result["inserted"] = ok
        result["errors"] = errors

        cur = conn.cursor()
        cur.execute(
            "UPDATE servers SET rebuild_conf_files='Y' WHERE generate_vicidial_conf='Y'"
        )
        conn.commit()
        cur.close()
    finally:
        if own_conn:
            conn.close()

    return result


def run(env, region: str = "all", limit: int | None = None, dry_run: bool = False, refill_hopper: bool = True):
    from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import VicidialService

    svc = VicidialService(env)
    if not svc.is_available():
        raise RuntimeError("MySQL VICIdial indisponible")

    regions = list(REGIONS) if region == "all" else [region]
    all_results = []
    for rk in regions:
        print("\n=== Import %s ===" % rk)
        res = import_region(svc, rk, limit=limit, dry_run=dry_run)
        all_results.append(res)
        print(
            "✓ %s list_id=%s : %s insérés, %s erreurs"
            % (rk, res.get("list_id"), res.get("inserted", 0), res.get("errors", 0))
        )

    if not dry_run and refill_hopper:
        Campaign = env["doorway.campaign"].sudo()
        camp = Campaign.search([("vicidial_campaign_id", "=", CAMPAIGN_ID)], limit=1)
        if camp:
            hopper = svc.reload_campaign_hopper(camp)
            print("✓ Hopper %s rechargé : %s leads" % (CAMPAIGN_ID, hopper))

    conn = svc._connect()
    try:
        stats = _count_campaign_lists(conn, CAMPAIGN_ID)
    finally:
        conn.close()
    print("\n=== Totaux DW_QCB2C ===")
    for lid, lname, cnt in stats["lists"]:
        print("  list %s (%s): %s" % (lid, lname, cnt))
    print("  vicidial_list total: %s" % stats["total_vicidial_list"])
    return all_results


def main():
    parser = argparse.ArgumentParser(description="Import QC listes → DW_QCB2C")
    parser.add_argument(
        "--region",
        choices=["lanaudiere", "rive_sud", "montreal", "all"],
        default=os.environ.get("IMPORT_REGION", "lanaudiere"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ["IMPORT_LIMIT"]) if os.environ.get("IMPORT_LIMIT") else None,
    )
    parser.add_argument("--dry-run", action="store_true", default=os.environ.get("IMPORT_DRY_RUN") == "1")
    parser.add_argument("--no-hopper", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    conn = _connect_mysql()
    regions = list(REGIONS) if args.region == "all" else [args.region]
    totals = {"inserted": 0, "errors": 0, "parsed": 0}

    for rk in regions:
        print("\n=== Import %s ===" % rk)
        files = _resolve_files(rk)
        print("Fichiers (%s):" % len(files))
        for f in files:
            print("  - %s" % f.relative_to(LISTES_BASE))

        res = import_region(conn, rk, limit=args.limit, dry_run=args.dry_run)
        totals["inserted"] += res.get("inserted", 0)
        totals["errors"] += res.get("errors", 0)
        totals["parsed"] += res.get("parsed_total", 0)
        print(
            "✓ %s list_id=%s : %s insérés, %s erreurs (parsés=%s)"
            % (rk, res.get("list_id"), res.get("inserted", 0), res.get("errors", 0), res.get("parsed_total", 0))
        )

    if not args.dry_run and not args.no_hopper and totals["inserted"] > 0:
        hopper = _reload_hopper(conn, CAMPAIGN_ID)
        print("\n✓ Hopper %s rechargé : %s leads" % (CAMPAIGN_ID, hopper))
    elif not args.dry_run:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id=%s", (CAMPAIGN_ID,))
        print("\nHopper %s actuel : %s leads" % (CAMPAIGN_ID, cur.fetchone()[0]))
        cur.close()

    stats = _count_campaign_lists(conn, CAMPAIGN_ID)
    conn.close()
    print("\n=== Totaux DW_QCB2C ===")
    qc_total = 0
    for lid, lname, cnt in stats["lists"]:
        qc_total += cnt
        print("  list %s (%s): %s" % (lid, lname, cnt))
    print("  sous-total DW_QCB2C: %s" % qc_total)
    print("  vicidial_list global: %s" % stats["total_vicidial_list"])
    print("\n=== Résumé import ===")
    print("  insérés: %s | erreurs: %s | parsés: %s" % (totals["inserted"], totals["errors"], totals["parsed"]))


if __name__ == "__main__":
    if "env" in dir():
        region = os.environ.get("IMPORT_REGION", "all")
        limit = int(os.environ["IMPORT_LIMIT"]) if os.environ.get("IMPORT_LIMIT") else None
        dry = os.environ.get("IMPORT_DRY_RUN") == "1"
        run(env, region=region, limit=limit, dry_run=dry)  # noqa: F821
    elif len(sys.argv) > 1:
        main()
    else:
        print("Usage: python3 import_pending_lists.py --region lanaudiere [--limit 1000] [--dry-run]")
