#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import fichier réel AvaTrade Espagne → campagne demo Abdallah (ABD_DEMO)."""
import re
from pathlib import Path

from espagne_avatrade_contacts import CONTACTS


def _normalize_es_phone(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("34") and len(digits) > 9:
        digits = digits[2:]
    if len(digits) > 9:
        digits = digits[-9:]
    return digits if len(digits) == 9 else ""


def _phone_display(digits):
    return "+34%s" % digits if digits else ""


def _split_name(full_name):
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""
    parts = full_name.split(None, 1)
    if len(parts) == 1:
        return "", parts[0][:30]
    return parts[0][:30], parts[1][:30]


def run(env):
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

    # Retirer contacts fictifs de test
    fake_phones = ("612345678", "623456789", "634567890")
    fake_contacts = Contact.search(
        [
            ("campaign_id", "=", camp.id),
            ("phone_number", "in", list(fake_phones)),
        ]
    )
    fake_partners = Partner.search(
        [
            ("company_id", "=", company.id),
            ("phone", "in", list(fake_phones) + ["+34" + p for p in fake_phones]),
        ]
    )
    fake_contacts.unlink()
    fake_partners.unlink()

    stats = {
        "total": len(CONTACTS),
        "partners_created": 0,
        "partners_reused": 0,
        "campaign_contacts": 0,
        "skipped": 0,
        "no_phone": 0,
    }
    vicidial_rows = []
    seen_phones = set()

    for row in CONTACTS:
        name = (row.get("name") or "").strip()
        digits = _normalize_es_phone(row.get("phone"))
        email = (row.get("email") or "").strip().lower()
        street = (row.get("street") or "").strip()
        source = row.get("source") or "AvaTrade"

        if not digits:
            stats["no_phone"] += 1
            continue
        if digits in seen_phones:
            stats["skipped"] += 1
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
            first, last = _split_name(name)
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
            continue

        first, last = _split_name(name)
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
