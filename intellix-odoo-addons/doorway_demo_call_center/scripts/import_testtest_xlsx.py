#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import /root/testtest.xlsx → campagne demo Abdallah (ABD_DEMO)."""
import re
from pathlib import Path

import openpyxl

XLSX_PATH = Path("/root/testtest.xlsx")
SOURCE = "testtest.xlsx"


def _normalize_es_phone(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("34") and len(digits) > 9:
        digits = digits[2:]
    if len(digits) > 9:
        digits = digits[-9:]
    return digits if len(digits) == 9 else ""


def _phone_display(digits):
    return "+34%s" % digits if digits else ""


def _split_name(first, last, fallback=""):
    first = (first or "").strip()[:30]
    last = (last or "").strip()[:30]
    if first or last:
        return first, last or first
    parts = (fallback or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0][:30]
    return parts[0][:30], parts[1][:30]


def _load_rows():
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        first = row[0] if len(row) > 0 else ""
        last = row[1] if len(row) > 1 else ""
        email = row[2] if len(row) > 2 else ""
        phone = row[3] if len(row) > 3 else ""
        street = row[4] if len(row) > 4 else ""
        city = row[5] if len(row) > 5 else ""
        name = " ".join(p for p in ((first or "").strip(), (last or "").strip()) if p)
        full_street = ", ".join(p for p in ((street or "").strip(), (city or "").strip()) if p)
        rows.append(
            {
                "name": name,
                "phone": phone,
                "email": email,
                "street": full_street,
                "source": SOURCE,
            }
        )
    return rows


def run(env):
    if not XLSX_PATH.is_file():
        raise RuntimeError("Fichier introuvable: %s" % XLSX_PATH)

    user = env["res.users"].sudo().search(
        [("login", "=", "echcherkia65@gmail.com")], limit=1
    )
    if not user:
        raise RuntimeError("Utilisateur Abdallah introuvable")
    company = user.company_id
    camp = env["doorway.campaign"].sudo().search(
        [("company_id", "=", company.id), ("vicidial_campaign_id", "=", "ABD_DEMO")],
        limit=1,
    )
    if not camp:
        raise RuntimeError("Campagne demo introuvable")

    Partner = env["res.partner"].sudo()
    Contact = env["doorway.campaign.contact"].sudo()
    Category = env["res.partner.category"].sudo()
    spain = env["res.country"].search([("code", "=", "ES")], limit=1)

    tag = Category.search([("name", "=", "Prospect Éligible Espagne")], limit=1)
    if not tag:
        tag = Category.create({"name": "Prospect Éligible Espagne"})

    contacts = _load_rows()
    stats = {
        "file": str(XLSX_PATH),
        "total_rows": len(contacts),
        "partners_created": 0,
        "partners_reused": 0,
        "campaign_contacts": 0,
        "skipped_existing": 0,
        "skipped_dup": 0,
        "no_phone": 0,
    }
    vicidial_rows = []
    seen_phones = set()

    for row in contacts:
        name = (row.get("name") or "").strip()
        digits = _normalize_es_phone(row.get("phone"))
        email = (row.get("email") or "").strip().lower()
        street = (row.get("street") or "").strip()
        source = row.get("source") or SOURCE

        if not digits:
            stats["no_phone"] += 1
            continue
        if digits in seen_phones:
            stats["skipped_dup"] += 1
            continue
        seen_phones.add(digits)

        partner = Partner.search(
            [
                ("company_id", "=", company.id),
                "|",
                ("phone", "ilike", digits),
                ("phone_sanitized", "ilike", digits),
            ],
            limit=1,
        )
        if not partner:
            first, last = _split_name("", "", name)
            partner = Partner.create(
                {
                    "name": name or "Prospect Espagne",
                    "company_id": company.id,
                    "phone": _phone_display(digits),
                    "email": email or False,
                    "street": street or False,
                    "comment": "[%s]" % source,
                    "country_id": spain.id if spain else False,
                    "lang": "es_ES",
                    "customer_rank": 1,
                    "category_id": [(4, tag.id)],
                }
            )
            stats["partners_created"] += 1
        else:
            stats["partners_reused"] += 1
            if tag not in partner.category_id:
                partner.write({"category_id": [(4, tag.id)]})

        if Contact.search_count(
            [("campaign_id", "=", camp.id), ("phone_number", "=", digits)]
        ):
            stats["skipped_existing"] += 1
            continue

        first, last = _split_name("", "", name)
        Contact.create(
            {
                "campaign_id": camp.id,
                "phone_number": digits,
                "first_name": first,
                "last_name": last or name[:30],
                "vendor_code": source[:20].replace(" ", "_"),
                "state": "new",
            }
        )
        stats["campaign_contacts"] += 1
        vicidial_rows.append(
            {
                "phone_number": digits,
                "first_name": first,
                "last_name": last or name[:30],
                "address1": street[:100] if street else "",
                "email": email[:70] if email else "",
                "comments": "[%s]" % source,
                "vendor_lead_code": source[:20],
                "source_id": "AVATRADE_ES",
                "status": "NEW",
                "country_code": "ES",
                "phone_code": "34",
            }
        )

    vicidial_result = {}
    svc = camp._vicidial_svc()
    if vicidial_rows and svc.is_available():
        vicidial_result = svc.inject_contacts(
            camp.vicidial_campaign_id,
            vicidial_rows,
            phone_code="34",
            list_name="ABD_DEMO",
        )

    camp.write({"state": "active"})
    env.cr.commit()
    return {
        "campaign": camp.name,
        "vicidial_campaign": camp.vicidial_campaign_id,
        **stats,
        "vicidial": vicidial_result,
        "total_contacts": Contact.search_count([("campaign_id", "=", camp.id)]),
    }
