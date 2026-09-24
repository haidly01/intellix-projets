#!/usr/bin/env python3
"""Backfill courriels jt.client depuis CSV sources (AGO / Inalco / polices)."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from import_data import JTImporter, normalize_email  # noqa: E402


def _load_email_rows(path: Path, id_field: str, email_fields: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            cid = (row.get(id_field) or '').strip()
            email = ''
            for field in email_fields:
                email = normalize_email(row.get(field) or '')
                if email:
                    break
            if cid and email:
                out[cid] = email
    return out


def _load_policy_emails(path: Path) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    if not path.exists():
        return rows
    with path.open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            email = normalize_email(
                row.get('client_email') or row.get('email') or ''
            )
            if not email:
                continue
            rows.append((
                (row.get('primary_insured_id') or row.get('client_id') or '').strip(),
                (row.get('client_first_name') or '').strip().title(),
                (row.get('client_last_name') or '').strip().title(),
                email,
            ))
    return rows


def main():
    parser = argparse.ArgumentParser(description='Backfill emails jt.client')
    parser.add_argument('--config', default='/etc/odoo-server.conf')
    parser.add_argument('--db', default='intellixcrm')
    parser.add_argument('--data-dir', default=str(SCRIPT_DIR))
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    email_by_uuid: dict[str, str] = {}
    for fname, id_field in (
        ('ago_clients.csv', 'client_id'),
        ('inalco_clients.csv', 'client_id'),
    ):
        email_by_uuid.update(_load_email_rows(
            data_dir / fname, id_field, ('email', 'client_email', 'courriel'),
        ))

    policy_rows = []
    for fname in ('ago_polices.csv', 'inalco_polices.csv', 'polices.csv', 'compte2_polices.csv'):
        policy_rows.extend(_load_policy_emails(data_dir / fname))

    sys.path.insert(0, '/odoo/odoo-server')
    import odoo
    from odoo import api, SUPERUSER_ID
    from odoo.modules.registry import Registry
    from odoo.tools import config

    config.parse_config(['-c', args.config, '-d', args.db])
    registry = Registry(args.db)

    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        if 'jt.client' not in env:
            print('ERREUR: module jason_thomas_assurance absent')
            sys.exit(1)
        imp = JTImporter(env)
        imp._cache_clients()

        updated = 0
        skipped_has_email = 0
        missing = 0

        for uuid, email in email_by_uuid.items():
            client_id = imp.client_by_uuid.get(uuid)
            if not client_id:
                missing += 1
                continue
            client = env['jt.client'].browse(client_id)
            if client.email:
                skipped_has_email += 1
                continue
            client.write({'email': email})
            updated += 1

        for uuid, first, last, email in policy_rows:
            client_id = None
            if uuid and uuid in imp.client_by_uuid:
                client_id = imp.client_by_uuid[uuid]
            else:
                client_id = imp.client_by_name.get(imp._name_key(first, last))
            if not client_id:
                missing += 1
                continue
            client = env['jt.client'].browse(client_id)
            if client.email:
                skipped_has_email += 1
                continue
            client.write({'email': email})
            updated += 1

        cr.commit()
        total_with = env['jt.client'].search_count([('email', '!=', False), ('email', '!=', '')])
        print(f'[done] emails mis à jour: {updated}')
        print(f'  déjà renseignés: {skipped_has_email}')
        print(f'  non trouvés en CRM: {missing}')
        print(f'  total clients avec email: {total_with}')


if __name__ == '__main__':
    main()
