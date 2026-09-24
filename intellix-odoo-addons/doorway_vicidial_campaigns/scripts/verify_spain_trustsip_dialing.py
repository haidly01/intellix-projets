#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie et corrige l'indicatif Espagne (34) sur toutes les campagnes TrustSIP."""
import subprocess
import sys

FIX = "--fix" in sys.argv

PY = (
    "from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import VicidialService\n"
    "svc = VicidialService(env)\n"
    "fix = " + ("True" if FIX else "False") + "\n"
    "if fix:\n"
    "    report = svc.ensure_spain_outbound_dialing()\n"
    "    env.cr.commit()\n"
    "    print('=== Correctif Espagne TrustSIP appliqué ===')\n"
    "else:\n"
    "    report = svc.audit_spain_dialing_config()\n"
    "    print('=== Audit Espagne TrustSIP (lecture seule) ===')\n"
    "print('OK global:', report.get('ok'))\n"
    "if report.get('error'):\n"
    "    print('Erreur:', report['error'])\n"
    "print()\n"
    "print('Campagnes:')\n"
    "for row in report.get('campaigns', []):\n"
    "    mark = 'OK' if row.get('valid') else 'KO'\n"
    "    print('  [%s] %s omit=%s dial_prefix=%s active=%s' % (mark, row.get('campaign_id'), row.get('omit_phone_code'), row.get('dial_prefix'), row.get('active')))\n"
    "carrier = report.get('carrier') or {}\n"
    "mark = 'OK' if carrier.get('valid') else 'KO'\n"
    "print()\n"
    "print('Carrier TrustSIP [%s] active=%s' % (mark, carrier.get('active')))\n"
    "for line in (carrier.get('dialplan_entry') or '').splitlines():\n"
    "    print('  ', line)\n"
    "print()\n"
    "print('Listes (phone_code):')\n"
    "for row in report.get('lists', []):\n"
    "    mark = 'OK' if row.get('valid') else 'KO'\n"
    "    print('  [%s] list %s (%s) campaign=%s phone_code=%s leads=%s' % (mark, row.get('list_id'), row.get('list_name'), row.get('campaign_id'), row.get('phone_code'), row.get('lead_count')))\n"
    "raise SystemExit(0 if report.get('ok') else 1)\n"
)


if __name__ == "__main__":
    proc = subprocess.run(
        [
            "sudo",
            "-u",
            "odoo",
            "python3",
            "/odoo/odoo-server/odoo-bin",
            "shell",
            "-c",
            "/etc/odoo-server.conf",
            "-d",
            "intellixcrm",
            "--no-http",
        ],
        input=PY,
        text=True,
        capture_output=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    sys.exit(proc.returncode)
