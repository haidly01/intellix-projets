#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nettoie les numéros invalides de la liste VICIdial ABD_DEMO (list_id 1011)."""
import re
import sys

LIST_ID = 1011
CAMPAIGN = "ABD_DEMO"


def normalize_es_phone(raw):
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("34") and len(digits) > 9:
        digits = digits[2:]
    if len(digits) > 9:
        digits = digits[-9:]
    if len(digits) != 9:
        return ""
    if not re.match(r"^[6789]\d{8}$", digits):
        return ""
    return digits


def run_mysql(sql, fetch=False):
    import subprocess

    cmd = [
        "mysql",
        "-h127.0.0.1",
        "-P3307",
        "-uvicidial",
        "-pa42246a8306dc369d33525c4cea6fef1",
        "asterisk",
        "-Nse",
        sql,
    ]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    if not fetch:
        return out.strip()
    rows = []
    for line in out.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def main():
    rows = run_mysql(
        "SELECT lead_id, phone_number FROM vicidial_list WHERE list_id=%s" % LIST_ID,
        fetch=True,
    )
    stats = {
        "total": len(rows),
        "kept": 0,
        "normalized": 0,
        "removed": 0,
        "dupes_removed": 0,
    }
    seen = {}
    to_delete = []
    updates = []

    for lead_id, phone in rows:
        norm = normalize_es_phone(phone)
        if not norm:
            to_delete.append(int(lead_id))
            stats["removed"] += 1
            continue
        if norm in seen:
            to_delete.append(int(lead_id))
            stats["dupes_removed"] += 1
            continue
        seen[norm] = int(lead_id)
        if norm != phone:
            updates.append((norm, int(lead_id)))
            stats["normalized"] += 1
        stats["kept"] += 1

    if to_delete:
        chunk = 500
        for i in range(0, len(to_delete), chunk):
            part = to_delete[i : i + chunk]
            ids = ",".join(str(x) for x in part)
            run_mysql(
                "DELETE FROM vicidial_hopper WHERE lead_id IN (%s);"
                " DELETE FROM vicidial_auto_calls WHERE lead_id IN (%s);"
                " DELETE FROM vicidial_list WHERE lead_id IN (%s);"
                % (ids, ids, ids)
            )

    for norm, lead_id in updates:
        run_mysql(
            "UPDATE vicidial_list SET phone_number='%s', status='NEW', "
            "called_since_last_reset='N', called_count=0 WHERE lead_id=%s"
            % (norm, lead_id)
        )

    run_mysql(
        "DELETE FROM vicidial_hopper WHERE campaign_id='%s';"
        " DELETE FROM vicidial_auto_calls WHERE campaign_id='%s';"
        " UPDATE vicidial_list SET status='NEW', called_since_last_reset='N' "
        "WHERE list_id=%s AND status NOT IN ('DNC','SALE');"
        " INSERT INTO vicidial_hopper (lead_id, campaign_id, status, list_id, "
        "gmt_offset_now, state, alt_dial, priority) "
        "SELECT lead_id, '%s', 'READY', list_id, 0.00, state, 'NONE', 0 "
        "FROM vicidial_list WHERE list_id=%s AND status='NEW';"
        % (CAMPAIGN, CAMPAIGN, LIST_ID, CAMPAIGN, LIST_ID)
    )

    hopper = run_mysql(
        "SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id='%s'" % CAMPAIGN
    )
    print(
        "ABD_DEMO cleanup: total=%s kept=%s normalized=%s removed=%s dupes=%s hopper=%s"
        % (
            stats["total"],
            stats["kept"],
            stats["normalized"],
            stats["removed"],
            stats["dupes_removed"],
            hopper,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
