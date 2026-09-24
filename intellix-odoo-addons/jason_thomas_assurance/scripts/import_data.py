#!/usr/bin/env python3
"""
Import données Jason Thomas Assurance dans Odoo (jt.* models).

Usage sur le serveur DEV/PROD :
  cd /odoo/custom/addons/jason_thomas_assurance/scripts
  python3 import_data.py --config /etc/odoo-server.conf --db intellixcrm

Les CSV doivent être dans le même dossier (noms ci-dessous).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

STATUS_MAP = {
    'en force': 'en_force',
    'en traitement': 'en_traitement',
    'accepté': 'accepte',
    'accepte': 'accepte',
    'refusé': 'refuse',
    'refuse': 'refuse',
    'échu': 'echu',
    'echu': 'echu',
}


def parse_date(value: str) -> str | bool:
    if not value or not str(value).strip():
        return False
    raw = str(value).strip()[:19]
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return False


def parse_datetime(value: str) -> str | bool:
    if not value or not str(value).strip():
        return False
    raw = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f%z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            if fmt.endswith('%z'):
                dt = datetime.strptime(raw[:26], fmt[: len(raw[:26])])
            else:
                dt = datetime.strptime(raw[:19], fmt[:19])
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    d = parse_date(raw)
    return f'{d} 00:00:00' if d else False


def normalize_gender(value: str) -> str | bool:
    v = (value or '').strip().lower()
    if v in ('homme', 'male', 'm', 'h'):
        return 'homme'
    if v in ('femme', 'female', 'f'):
        return 'femme'
    return False


def normalize_status(value: str) -> str:
    key = (value or '').strip().lower()
    if key in STATUS_MAP:
        return STATUS_MAP[key]
    if 'vigueur' in key or key == 'rf_en_vigueur':
        return 'en_force'
    return 'autre'


def split_name(full: str) -> tuple[str, str]:
    parts = (full or '').strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0].title(), ''
    return parts[0].title(), ' '.join(parts[1:]).title()


def float_val(value) -> float:
    try:
        return float(str(value).replace(',', '.').strip() or 0)
    except ValueError:
        return 0.0


EMAIL_KEYS = (
    'email', 'emailAddress', 'EmailAddress', 'personalEmail', 'workEmail',
    'preferredEmail', 'courriel', 'courrielPersonnel', 'mail', 'clientEmail',
)


def extract_email(obj: dict | None) -> str:
    if not obj:
        return ''
    for key in EMAIL_KEYS:
        val = obj.get(key)
        if val and '@' in str(val):
            return str(val).strip().lower()
    for nested in ('contact', 'contactInfo', 'primaryContact', 'communication'):
        sub = obj.get(nested)
        if isinstance(sub, dict):
            found = extract_email(sub)
            if found:
                return found
    return ''


def normalize_email(value: str) -> str:
    email = (value or '').strip().lower()
    if not email or '@' not in email or ' ' in email:
        return ''
    return email


def normalize_policy_number(value: str) -> str:
    return str(value or '').replace('"', '').strip()


def policy_aliases(value: str) -> set[str]:
    num = normalize_policy_number(value)
    aliases = {num, num.lstrip('0') or '0'}
    if num.isdigit():
        aliases.add(num.zfill(9))
    return aliases


def institution_from_row(source_col: str, product: str = '') -> str:
    src = (source_col or '').upper()
    if src == 'AGO':
        return 'ago'
    if 'RF' in src or 'INALCO' in src or 'IA' in src:
        return 'inalco'
    return 'ia_groupe'


class JTImporter:
    def __init__(self, env):
        self.env = env
        self.Client = env['jt.client']
        self.Police = env['jt.police']
        self.Transaction = env['jt.transaction']
        self.Activite = env['jt.activite']
        self.client_by_uuid: dict[str, int] = {}
        self.client_by_name: dict[str, int] = {}
        self.police_by_number: dict[str, int] = {}

    def _name_key(self, first: str, last: str) -> str:
        return f'{(first or "").strip().upper()}|{(last or "").strip().upper()}'

    def _cache_clients(self):
        for client in self.Client.search([]):
            if client.client_id_source:
                self.client_by_uuid[client.client_id_source] = client.id
            if client.full_name:
                self.client_by_name[client.full_name.upper()] = client.id
            self.client_by_name[self._name_key(client.first_name, client.last_name)] = client.id

    def _cache_polices(self):
        for police in self.Police.search([]):
            if police.policy_number:
                self._register_police(police.policy_number, police.coverage_number, police.id)

    def _register_police(self, policy_number: str, coverage_number: str | None, police_id: int):
        coverage = str(coverage_number or '1').strip()
        dedup_key = f'{normalize_policy_number(policy_number)}#{coverage}'
        self.police_by_number[dedup_key] = police_id
        for alias in policy_aliases(policy_number):
            if alias not in self.police_by_number:
                self.police_by_number[alias] = police_id

    def _police_lookup(self, policy_number: str) -> int | None:
        num = normalize_policy_number(policy_number)
        for alias in policy_aliases(num):
            if alias in self.police_by_number:
                return self.police_by_number[alias]
        return None

    def _police_exists(self, policy_number: str, coverage_number: str) -> bool:
        key = f'{normalize_policy_number(policy_number)}#{coverage_number or "1"}'
        return key in self.police_by_number

    def upsert_client(self, vals: dict) -> int:
        uuid = vals.get('client_id_source')
        if uuid and uuid in self.client_by_uuid:
            existing = self.Client.browse(self.client_by_uuid[uuid])
            merge = {}
            if existing.source != vals.get('source') and vals.get('source') in ('ago', 'inalco'):
                sources = {existing.source, vals['source']}
                if sources >= {'ago', 'inalco'}:
                    merge['source'] = 'ago_inalco'
            for field in ('cell_phone', 'home_phone', 'office_phone', 'postal_code',
                          'spouse_first_name', 'spouse_last_name', 'birth_date', 'gender', 'email'):
                if not existing[field] and vals.get(field):
                    merge[field] = vals[field]
            if merge:
                existing.write(merge)
            return existing.id

        name_key = self._name_key(vals.get('first_name', ''), vals.get('last_name', ''))
        if name_key.replace('|', '') and name_key in self.client_by_name:
            existing = self.Client.browse(self.client_by_name[name_key])
            if uuid and not existing.client_id_source:
                existing.write({'client_id_source': uuid})
                self.client_by_uuid[uuid] = existing.id
            return existing.id

        full_key = (vals.get('full_name') or f"{vals.get('first_name', '')} {vals.get('last_name', '')}").strip().upper()
        if full_key and full_key in self.client_by_name:
            existing = self.Client.browse(self.client_by_name[full_key])
            if uuid and not existing.client_id_source:
                existing.write({'client_id_source': uuid})
                self.client_by_uuid[uuid] = existing.id
            return existing.id

        client_id = self.Client.create(vals).id
        if uuid:
            self.client_by_uuid[uuid] = client_id
        if name_key.replace('|', ''):
            self.client_by_name[name_key] = client_id
        if full_key:
            self.client_by_name[full_key] = client_id
        return client_id

    def ensure_client_from_policy(self, row: dict, source: str) -> int | None:
        client_id = self._client_id_for_policy(row, source)
        if client_id:
            return client_id
        first = (row.get('client_first_name') or '').strip().title()
        last = (row.get('client_last_name') or '').strip().title()
        if not first and not last:
            client_name = (row.get('client_name') or '').strip()
            first, last = split_name(client_name)
        if not first and not last:
            return None
        return self.upsert_client({
            'source': source if source != 'inalco' else 'inalco',
            'first_name': first,
            'last_name': last,
            'birth_date': parse_date(row.get('client_birth_date', '')),
            'cell_phone': (row.get('client_mobile') or row.get('cell_phone') or '').strip(),
            'home_phone': (row.get('client_home_phone') or row.get('home_phone') or '').strip(),
            'email': normalize_email(row.get('client_email') or row.get('email') or ''),
        })

    def import_ago_clients(self, path: Path) -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                vals = {
                    'source': 'ago',
                    'client_id_source': row.get('client_id', '').strip(),
                    'first_name': (row.get('first_name') or '').strip().title(),
                    'last_name': (row.get('last_name') or '').strip().title(),
                    'birth_date': parse_date(row.get('birth_date', '')),
                    'gender': normalize_gender(row.get('gender', '')),
                    'cell_phone': (row.get('cell_phone') or '').strip(),
                    'home_phone': (row.get('home_phone') or '').strip(),
                    'office_phone': (row.get('office_phone') or '').strip(),
                    'postal_code': (row.get('postal_code') or '').strip(),
                    'email': normalize_email(row.get('email') or row.get('client_email') or ''),
                    'spouse_first_name': (row.get('spouse_first_name') or '').strip().title(),
                    'spouse_last_name': (row.get('spouse_last_name') or '').strip().title(),
                }
                before = len(self.client_by_uuid)
                self.upsert_client(vals)
                if vals['client_id_source'] and vals['client_id_source'] not in self.client_by_uuid:
                    pass
                if vals['client_id_source'] and self.client_by_uuid.get(vals['client_id_source']):
                    if before != len(self.client_by_uuid):
                        created += 1
                elif vals['client_id_source']:
                    created += 1
        print(f'  → clients AGO traités depuis {path.name}')
        return created

    def import_inalco_clients(self, path: Path) -> int:
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                vals = {
                    'source': 'inalco',
                    'client_id_source': row.get('client_id', '').strip(),
                    'first_name': (row.get('first_name') or '').strip().title(),
                    'last_name': (row.get('last_name') or '').strip().title(),
                    'birth_date': parse_date(row.get('birth_date', '')),
                    'gender': normalize_gender(row.get('gender', '')),
                    'cell_phone': (row.get('cell_phone') or '').strip(),
                    'home_phone': (row.get('home_phone') or '').strip(),
                    'postal_code': (row.get('postal_code') or '').strip(),
                    'email': normalize_email(row.get('email') or row.get('client_email') or ''),
                }
                self.upsert_client(vals)
        print(f'  → clients Inalco enrichis depuis {path.name}')
        return 0

    def import_assomption_clients(self, path: Path) -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                owner = (row.get('Nom du propriétaire') or row.get('Nom du proprietaire') or '').strip()
                co_owner = (row.get('Nom du co-propriétaire') or row.get('Nom du co-proprietaire') or '').strip()
                insured = (row.get('Nom des assurés') or row.get('Nom des assures') or '').strip()
                name = insured or owner or co_owner
                first, last = split_name(name)
                if not first and not last:
                    continue
                before_ids = set(self.client_by_name.values()) | set(self.client_by_uuid.values())
                client_id = self.upsert_client({
                    'source': 'assomption_vie',
                    'first_name': first,
                    'last_name': last,
                })
                if client_id not in before_ids:
                    created += 1
        print(f'  → {created} clients Assomption Vie créés depuis {path.name}')
        return created

    def _client_id_for_policy(self, row: dict, source: str) -> int | None:
        first = (row.get('client_first_name') or '').strip().title()
        last = (row.get('client_last_name') or '').strip().title()
        name_key = self._name_key(first, last)
        if name_key.replace('|', '') and name_key in self.client_by_name:
            return self.client_by_name[name_key]

        uuid = (row.get('primary_insured_id') or row.get('client_id') or '').strip()
        if uuid and uuid in self.client_by_uuid:
            return self.client_by_uuid[uuid]

        client_name = (row.get('client_name') or '').strip()
        if client_name:
            fn, ln = split_name(client_name)
            name_key = self._name_key(fn, ln)
            if name_key.replace('|', '') and name_key in self.client_by_name:
                return self.client_by_name[name_key]
        return None

    def import_ago_polices(self, path: Path) -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                policy_number = (row.get('policy_number') or '').strip()
                if not policy_number or self._police_lookup(policy_number):
                    continue
                client_id = self.ensure_client_from_policy(row, 'ago')
                if not client_id:
                    continue
                vals = {
                    'client_id': client_id,
                    'policy_number': policy_number,
                    'policy_status': normalize_status(row.get('policy_status', '')),
                    'product': (row.get('product') or '').strip(),
                    'product_code': (row.get('product_code') or '').strip(),
                    'institution': 'ago',
                    'submission_date': parse_date(row.get('submission_date', '')),
                    'eff_date': parse_date(row.get('eff_date') or row.get('ho_receipt_date', '')),
                    'term_date': parse_date(row.get('term_date', '')),
                    'face_amount': float_val(row.get('face_amount')),
                    'premium': float_val(row.get('premium')),
                    'underwriting_status': (row.get('underwriting_status') or '').strip(),
                    'source': 'ago',
                }
                pid = self.Police.create(vals).id
                self._register_police(policy_number, None, pid)
                created += 1
        print(f'  → {created} polices AGO créées')
        return created

    def import_inalco_polices(self, path: Path) -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                policy_number = (row.get('policy_number') or row.get('contract_number') or '').strip()
                if not policy_number or self._police_lookup(policy_number):
                    continue
                client_id = self.ensure_client_from_policy(row, 'inalco')
                if not client_id:
                    continue
                src_col = row.get('source', '')
                vals = {
                    'client_id': client_id,
                    'policy_number': policy_number,
                    'policy_status': normalize_status(row.get('status', '')),
                    'product': (row.get('product') or '').strip(),
                    'institution': institution_from_row(src_col, row.get('product', '')),
                    'submission_date': parse_date(row.get('submission_date', '')),
                    'eff_date': parse_date(row.get('eff_date', '')),
                    'term_date': parse_date(row.get('term_date', '')),
                    'premium': float_val(row.get('premium')),
                    'contract_type': (row.get('contract_type') or '').strip(),
                    'source': 'inalco',
                }
                pid = self.Police.create(vals).id
                self._register_police(policy_number, None, pid)
                created += 1
        print(f'  → {created} polices Inalco créées')
        return created

    def import_assomption_polices(self, path: Path, account_code: str) -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                owner = (row.get('Nom du propriétaire') or row.get('Nom du proprietaire') or '').strip()
                if not owner:
                    continue
                first, last = split_name(owner)
                client_id = self.client_by_name.get(self._name_key(first, last))
                if not client_id:
                    client_id = self.client_by_name.get(owner.upper())
                if not client_id:
                    client_id = self.upsert_client({
                        'source': 'assomption_vie',
                        'first_name': first,
                        'last_name': last,
                    })

                policy_num = normalize_policy_number(row.get('Numéro de police', ''))
                if not policy_num:
                    continue
                coverage = str(row.get('Numéro de couverture', '') or '1').strip()
                if self._police_exists(policy_num, coverage):
                    continue

                vals = {
                    'client_id': client_id,
                    'policy_number': policy_num,
                    'policy_status': 'en_force',
                    'product': (row.get('Produit') or '').strip(),
                    'face_amount': float_val(row.get('Capital assuré') or row.get('Capital assure')),
                    'annual_premium': float_val(row.get('Prime annuelle')),
                    'premium': float_val(row.get('Prime annuelle')),
                    'submission_date': parse_date(row.get("Date d'émission", '') or row.get("Date d'emission", '')),
                    'eff_date': parse_date(row.get("Date d'émission", '') or row.get("Date d'emission", '')),
                    'term_date': parse_date(row.get('Date de renouvellement', '')),
                    'co_owner_name': (row.get('Nom du co-propriétaire') or row.get('Nom du co-proprietaire') or '').strip(),
                    'insured_names': (row.get('Nom des assurés') or row.get('Nom des assures') or '').strip(),
                    'coverage_number': coverage,
                    'agent_code': (row.get("Code d'agent") or '').strip(),
                    'courtier': (row.get('Courtier') or '').strip(),
                    'institution': 'assomption_vie',
                    'source': 'assomption_vie',
                    'assomption_account': account_code,
                }
                pid = self.Police.create(vals).id
                self._register_police(policy_num, coverage, pid)
                created += 1
        print(f'  → {created} polices Assomption ({account_code}) depuis {path.name}')
        return created

    def import_assomption_transactions(self, path: Path, account_label: str) -> int:
        created = 0
        with path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                policy_num = str(row.get('policy_number', '')).strip()
                police_id = self._police_lookup(policy_num)
                if not police_id:
                    continue
                vals = {
                    'police_id': police_id,
                    'client_name': (row.get('client_name') or '').strip(),
                    'event_type': 'Relevé annuel',
                    'event_date': parse_datetime(row.get('date', '')),
                    'reference': policy_num,
                    'source': 'assomption_vie',
                    'pdf_url': (row.get('pdf_url') or '').strip(),
                }
                self.Transaction.create(vals)
                created += 1
        print(f'  → {created} transactions Assomption ({account_label}) depuis {path.name}')
        return created

    def import_transactions(self, path: Path, source: str, policy_field: str = 'policy_number') -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                ref = (row.get('reference') or row.get(policy_field) or row.get('policy_number') or '').strip()
                policy_number = (row.get('policy_number') or ref or '').strip()
                police_id = self._police_lookup(policy_number) or self._police_lookup(ref)
                vals = {
                    'police_id': police_id or False,
                    'client_name': (row.get('client_name') or '').strip(),
                    'event_type': (row.get('event_type') or '').strip(),
                    'event_date': parse_datetime(row.get('event_date') or row.get('date', '')),
                    'reference': ref,
                    'source': source,
                    'pdf_url': (row.get('pdf_url') or '').strip(),
                }
                if not vals['event_type'] and not vals['event_date']:
                    continue
                self.Transaction.create(vals)
                created += 1
        print(f'  → {created} transactions ({source}) depuis {path.name}')
        return created

    def import_activites(self, path: Path) -> int:
        created = 0
        with path.open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                policy_number = (row.get('policy_number') or '').strip()
                police_id = self._police_lookup(policy_number)
                vals = {
                    'police_id': police_id or False,
                    'activity_type': (row.get('activity_type') or '').strip(),
                    'activity_subtype': (row.get('activity_subtype') or '').strip(),
                    'activity_type_tc': (row.get('activity_type_tc') or '').strip(),
                    'opened': parse_datetime(row.get('opened', '')),
                    'closed': parse_datetime(row.get('closed', '')),
                    'user_code': (row.get('user_code') or '').strip(),
                    'details_fr': (row.get('details_fr') or '').strip(),
                    'details_en': (row.get('details_en') or '').strip(),
                }
                self.Activite.create(vals)
                created += 1
        print(f'  → {created} activités AGO')
        return created

    def run(self, data_dir: Path):
        self._cache_clients()
        self._cache_polices()
        mapping = {
            'ago_clients.csv': self.import_ago_clients,
            'inalco_clients.csv': self.import_inalco_clients,
            'clients.csv': self.import_assomption_clients,
            'compte2_clients.csv': self.import_assomption_clients,
            'ago_polices.csv': self.import_ago_polices,
            'inalco_polices.csv': self.import_inalco_polices,
            'polices.csv': lambda p: self.import_assomption_polices(p, '6tz2'),
            'compte2_polices.csv': lambda p: self.import_assomption_polices(p, 'a0yx'),
            'ago_transactions.csv': lambda p: self.import_transactions(p, 'ago'),
            'inalco_transactions.csv': lambda p: self.import_transactions(p, 'inalco'),
            'transactions.csv': lambda p: self.import_assomption_transactions(p, '6TZ2'),
            'compte2_transactions.csv': lambda p: self.import_assomption_transactions(p, 'A0YX'),
            'ago_activites.csv': self.import_activites,
        }
        for filename, handler in mapping.items():
            path = data_dir / filename
            if path.exists():
                print(f'[import] {filename}')
                handler(path)
            else:
                print(f'[skip] {filename} absent')
        self.env.cr.commit()
        print('[done] Import terminé.')
        print(f'  Clients: {self.Client.search_count([])}')
        print(f'  Polices: {self.Police.search_count([])}')
        print(f'  Transactions: {self.Transaction.search_count([])}')
        print(f'  Activités: {self.Activite.search_count([])}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/odoo-server.conf')
    parser.add_argument('--db', default='intellixcrm')
    parser.add_argument('--data-dir', default=str(SCRIPT_DIR))
    args = parser.parse_args()

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
            print('ERREUR: module jason_thomas_assurance non installé (jt.client absent)')
            sys.exit(1)
        JTImporter(env).run(Path(args.data_dir))


if __name__ == '__main__':
    main()
