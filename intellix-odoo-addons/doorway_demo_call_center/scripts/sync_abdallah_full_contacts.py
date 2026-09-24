#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Copie tous les contacts DW_ESREN → campagne demo Abdallah (ABD_DEMO)."""
import re


def _phone_display(digits):
    return "+34%s" % digits if digits else ""


def run(env):
    user = env["res.users"].sudo().search(
        [("login", "=", "echcherkia65@gmail.com")], limit=1
    )
    if not user:
        raise RuntimeError("Utilisateur Abdallah introuvable")

    company = user.company_id
    src = env["doorway.campaign"].sudo().search(
        [("vicidial_campaign_id", "=", "DW_ESREN")], limit=1
    )
    dst = env["doorway.campaign"].sudo().search(
        [("company_id", "=", company.id)], limit=1
    )
    if not src or not dst:
        raise RuntimeError("Campagnes source/destination introuvables")

    Partner = env["res.partner"].sudo()
    Contact = env["doorway.campaign.contact"].sudo()
    Category = env["res.partner.category"].sudo()
    spain = env["res.country"].search([("code", "=", "ES")], limit=1)
    tag = Category.search([("name", "=", "Prospect Éligible Espagne")], limit=1)
    if not tag:
        tag = Category.create({"name": "Prospect Éligible Espagne"})

    dst_phones = set(
        Contact.search([("campaign_id", "=", dst.id)]).mapped("phone_number")
    )
    src_contacts = Contact.search([("campaign_id", "=", src.id)], order="id")

    stats = {
        "source_total": len(src_contacts),
        "already_present": 0,
        "campaign_contacts_added": 0,
        "partners_created": 0,
        "partners_reused": 0,
        "vicidial_injected": 0,
    }
    vicidial_rows = []

    for sc in src_contacts:
        digits = re.sub(r"\D", "", sc.phone_number or "")
        if len(digits) > 9:
            digits = digits[-9:]
        if not digits:
            continue
        if digits in dst_phones:
            stats["already_present"] += 1
            continue

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
            src_partner = Partner.search(
                [
                    "|",
                    ("phone", "ilike", digits),
                    ("phone_sanitized", "ilike", digits),
                ],
                limit=1,
            )
            vals = {
                "name": (
                    (sc.first_name or "") + " " + (sc.last_name or "")
                ).strip()
                or "Prospect Espagne",
                "company_id": company.id,
                "phone": _phone_display(digits),
                "email": sc.email or False,
                "country_id": spain.id if spain else False,
                "lang": "es_ES",
                "customer_rank": 1,
                "category_id": [(4, tag.id)],
            }
            if src_partner:
                vals.update(
                    {
                        "street": src_partner.street or False,
                        "comment": src_partner.comment or "[AvaTrade]",
                    }
                )
            partner = Partner.create(vals)
            stats["partners_created"] += 1
        else:
            stats["partners_reused"] += 1
            if tag not in partner.category_id:
                partner.write({"category_id": [(4, tag.id)]})

        Contact.create(
            {
                "campaign_id": dst.id,
                "phone_number": digits,
                "first_name": sc.first_name or "",
                "last_name": sc.last_name or "",
                "email": sc.email or "",
                "vendor_code": sc.vendor_code or "AvaTrade",
                "state": "new",
            }
        )
        dst_phones.add(digits)
        stats["campaign_contacts_added"] += 1
        vicidial_rows.append(
            {
                "phone_number": digits,
                "first_name": sc.first_name or "",
                "last_name": sc.last_name or "",
                "email": sc.email or "",
                "vendor_lead_code": (sc.vendor_code or "AvaTrade")[:20],
                "source_id": "AVATRADE_ES",
                "status": "NEW",
                "country_code": "ES",
                "phone_code": "34",
            }
        )

    vicidial_result = {}
    svc = dst._vicidial_svc()
    if vicidial_rows and svc.is_available():
        vicidial_result = svc.inject_contacts(
            dst.vicidial_campaign_id,
            vicidial_rows,
            phone_code="34",
            list_name="ABD_DEMO",
        )
        stats["vicidial_injected"] = vicidial_result.get("ok", 0)

    dst.write({"state": "active"})
    env.cr.commit()
    stats["total_contacts"] = Contact.search_count([("campaign_id", "=", dst.id)])
    return {
        "campaign": dst.name,
        "vicidial_campaign": dst.vicidial_campaign_id,
        "vicidial": vicidial_result,
        **stats,
    }
