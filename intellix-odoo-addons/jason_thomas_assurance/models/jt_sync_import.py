# -*- coding: utf-8 -*-
"""Import polices depuis l'extension (Assomption XLS extrait dans le navigateur)."""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta

from odoo import api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

ASSOMPTION_ACCOUNT_BY_AGENT = {
    '6TZ2': '6tz2',
    'A0YX': 'a0yx',
}

PORTAIL_BY_ACCOUNT = {
    '6tz2': 'assomption',
    'a0yx': 'assomption_2',
}


def _clean_str(value) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if text.endswith('.0') and text[:-2].isdigit():
        text = text[:-2]
    return text.strip().strip('"').strip("'").strip()


def _split_name(full: str) -> tuple[str, str]:
    full = _clean_str(full)
    if not full:
        return '', ''
    parts = full.split(None, 1)
    if len(parts) == 1:
        return '', parts[0]
    return parts[0], parts[1]


def _parse_amount(value) -> float:
    if value is None or value is False:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace('$', '').replace(',', '').replace(' ', '').strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_date(value, datemode: int = 0):
    if value is None or value is False or value == '':
        return False
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, (int, float)):
        try:
            import xlrd
            dt = xlrd.xldate_as_datetime(value, datemode)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            try:
                # Excel serial fallback (1900 system)
                base = datetime(1899, 12, 30)
                return (base + timedelta(days=float(value))).strftime('%Y-%m-%d')
            except Exception:
                return False
    text = _clean_str(value)[:19]
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return False


def _normalize_policy_number(value) -> str:
    text = _clean_str(value)
    text = text.replace('"', '').replace("'", '').strip()
    return text


class JTSyncImport(models.AbstractModel):
    _name = 'jt.sync.import'
    _description = 'Import sync extension → CRM'

    @api.model
    def parse_assomption_xls(self, raw: bytes) -> list[dict]:
        try:
            import xlrd
        except ImportError as exc:
            raise ValidationError('xlrd manquant sur le serveur Odoo') from exc

        book = xlrd.open_workbook(file_contents=raw)
        sheet = book.sheet_by_index(0)
        if sheet.nrows < 2:
            return []

        headers = [
            _clean_str(sheet.cell_value(0, col)).upper().replace(' ', '_')
            for col in range(sheet.ncols)
        ]
        # Map flexible FR / EN
        aliases = {
            'AGENT_CODE': ('AGENT_CODE', "CODE_D'AGENT", 'CODE_AGENT'),
            'BROKER': ('BROKER', 'COURTIER'),
            'POLICY_NUMBER': ('POLICY_NUMBER', 'NUMÉRO_DE_POLICE', 'NUMERO_DE_POLICE', 'NUMÉRO_POLICE'),
            'OWNERNAME': ('OWNERNAME', 'NOM_DU_PROPRIÉTAIRE', 'NOM_DU_PROPRIETAIRE', 'OWNER_NAME'),
            'COOWNERNAME': ('COOWNERNAME', 'NOM_DU_CO-PROPRIÉTAIRE', 'NOM_DU_CO_PROPRIETAIRE', 'CO_OWNER_NAME'),
            'COVERAGE_NUMBER': ('COVERAGE_NUMBER', 'NUMÉRO_DE_COUVERTURE', 'NUMERO_DE_COUVERTURE'),
            'COVERAGE_PLAN': ('COVERAGE_PLAN', 'PRODUIT', 'PRODUCT'),
            'CAPITAL_INSURED': ('CAPITAL_INSURED', 'CAPITAL_ASSURÉ', 'CAPITAL_ASSURE', 'FACE_AMOUNT'),
            'ANNUALIZED_PREMIUM': ('ANNUALIZED_PREMIUM', 'PRIME_ANNUELLE', 'PREMIUM'),
            'ISSUE_DATE': ('ISSUE_DATE', "DATE_D'ÉMISSION", "DATE_D'EMISSION", 'EFF_DATE'),
            'RENEWAL_DATE': ('RENEWAL_DATE', 'DATE_DE_RENOUVELLEMENT', 'TERM_DATE'),
            'INSURED_NAMES': ('INSURED_NAMES', 'NOM_DES_ASSURÉS', 'NOM_DES_ASSURES'),
        }
        col_idx: dict[str, int] = {}
        for key, names in aliases.items():
            for name in names:
                if name in headers:
                    col_idx[key] = headers.index(name)
                    break

        if 'POLICY_NUMBER' not in col_idx:
            raise ValidationError(
                f'Colonnes Assomption invalides (pas de numéro de police). Headers={headers}'
            )

        rows: list[dict] = []
        for r in range(1, sheet.nrows):
            def cell(key: str):
                idx = col_idx.get(key)
                if idx is None:
                    return None
                return sheet.cell_value(r, idx)

            policy_number = _normalize_policy_number(cell('POLICY_NUMBER'))
            if not policy_number:
                continue
            owner = _clean_str(cell('OWNERNAME'))
            insured = _clean_str(cell('INSURED_NAMES'))
            first, last = _split_name(owner or insured)
            agent = _clean_str(cell('AGENT_CODE')).upper().replace(' ', '')
            account = ASSOMPTION_ACCOUNT_BY_AGENT.get(agent)
            if not account and agent:
                # fuzzy
                if '6TZ2' in agent:
                    account = '6tz2'
                elif 'A0YX' in agent:
                    account = 'a0yx'

            coverage = _clean_str(cell('COVERAGE_NUMBER')) or '1'
            if coverage.endswith('.0'):
                coverage = coverage[:-2]

            rows.append({
                'numero_police': policy_number,
                'coverage_number': coverage,
                'client_prenom': first,
                'client_nom': last,
                'owner_name': owner,
                'co_owner_name': _clean_str(cell('COOWNERNAME')),
                'insured_names': insured,
                'produit': _clean_str(cell('COVERAGE_PLAN')),
                'montant': _parse_amount(cell('CAPITAL_INSURED')),
                'prime_annuelle': _parse_amount(cell('ANNUALIZED_PREMIUM')),
                'date_emission': _parse_date(cell('ISSUE_DATE'), book.datemode),
                'date_echeance': _parse_date(cell('RENEWAL_DATE'), book.datemode),
                'statut': 'en_force',
                'fournisseur': PORTAIL_BY_ACCOUNT.get(account or '', 'assomption'),
                'institution': 'assomption_vie',
                'assomption_account': account,
                'agent_code': agent,
                'courtier': _clean_str(cell('BROKER')),
            })
        return rows

    @api.model
    def _find_or_create_client(self, police: dict) -> int | bool:
        Client = self.env['jt.client'].sudo()
        first = _clean_str(police.get('client_prenom'))
        last = _clean_str(police.get('client_nom'))
        if not first and not last:
            return False
        domain = [
            ('first_name', '=ilike', first or ''),
            ('last_name', '=ilike', last or ''),
        ]
        existing = Client.search(domain, limit=1)
        if existing:
            return existing.id
        return Client.create({
            'source': 'assomption_vie',
            'first_name': first or False,
            'last_name': last or False,
            'email': _clean_str(police.get('client_email')) or False,
            'cell_phone': _clean_str(police.get('client_phone')) or False,
            'birth_date': police.get('client_birth_date') or False,
        }).id

    @api.model
    def upsert_polices(self, polices: list[dict]) -> dict:
        Police = self.env['jt.police'].sudo()
        stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'skipped': 0, 'errors': 0}
        for police in polices:
            try:
                numero = _normalize_policy_number(police.get('numero_police'))
                if not numero:
                    stats['skipped'] += 1
                    continue
                coverage = _clean_str(police.get('coverage_number')) or False
                domain = [('policy_number', '=', numero)]
                if coverage:
                    domain.append(('coverage_number', '=', coverage))
                existing = Police.search(domain, limit=1)

                client_id = self._find_or_create_client(police)
                vals = {
                    'policy_number': numero,
                    'coverage_number': coverage or False,
                    'product': _clean_str(police.get('produit')) or False,
                    'product_code': _clean_str(police.get('product_code')) or False,
                    'policy_status': police.get('statut') or 'en_force',
                    'face_amount': _parse_amount(police.get('montant')),
                    'premium': _parse_amount(police.get('prime_annuelle')),
                    'annual_premium': _parse_amount(police.get('prime_annuelle')),
                    'eff_date': police.get('date_emission') or False,
                    'term_date': police.get('date_echeance') or False,
                    'institution': police.get('institution') or 'assomption_vie',
                    'source': 'assomption_vie',
                    'coverage_summary': _clean_str(police.get('coverage_summary')) or False,
                    'agent_code': _clean_str(police.get('agent_code')) or False,
                    'courtier': _clean_str(police.get('courtier')) or False,
                }
                for key in (
                    'insured_names', 'owner_name', 'payer_name',
                    'owner_address', 'payer_address', 'co_owner_name',
                ):
                    if police.get(key) and key in Police._fields:
                        vals[key] = police[key]
                if police.get('assomption_account') and 'assomption_account' in Police._fields:
                    vals['assomption_account'] = police['assomption_account']
                if client_id:
                    vals['client_id'] = client_id

                # Ne garder que les champs réellement présents sur ce serveur
                vals = {k: v for k, v in vals.items() if k in Police._fields}
                if existing:
                    write_vals = dict(vals)
                    if not write_vals.get('face_amount') and existing.face_amount:
                        write_vals.pop('face_amount', None)
                    if not write_vals.get('premium') and existing.premium:
                        write_vals.pop('premium', None)
                    if not write_vals.get('annual_premium') and existing.annual_premium:
                        write_vals.pop('annual_premium', None)
                    existing.write(write_vals)
                    stats['updated'] += 1
                else:
                    if not client_id:
                        stats['skipped'] += 1
                        continue
                    Police.create(vals)
                    stats['created'] += 1
            except Exception:
                _logger.exception('JT sync upsert police %s', police.get('numero_police'))
                stats['errors'] += 1
        return stats

    @api.model
    def import_assomption_xls_payload(self, payload: dict) -> dict:
        """Reçoit le XLS base64 depuis l'extension et upsert les polices."""
        b64 = payload.get('data_base64') or payload.get('data') or ''
        if not b64:
            raise ValidationError('data_base64 manquant')
        try:
            raw = base64.b64decode(b64)
        except Exception as exc:
            raise ValidationError('base64 invalide') from exc
        if len(raw) < 8:
            raise ValidationError('fichier trop petit')
        # OLE magic D0 CF 11 E0
        if raw[:4] != b'\xd0\xcf\x11\xe0':
            raise ValidationError('fichier non Excel (.xls attendu)')

        rows = self.parse_assomption_xls(raw)
        account_hint = (payload.get('account_code') or '').strip().lower()
        if account_hint in ('6tz2', 'a0yx'):
            for row in rows:
                if not row.get('assomption_account'):
                    row['assomption_account'] = account_hint
                    row['fournisseur'] = PORTAIL_BY_ACCOUNT[account_hint]

        stats = self.upsert_polices(rows)
        accounts = sorted({r.get('assomption_account') for r in rows if r.get('assomption_account')})
        _logger.info(
            'JT Assomption XLS import: %s lignes → %s (accounts=%s)',
            len(rows), stats, accounts,
        )
        return {
            'ok': True,
            'nb_rows': len(rows),
            'accounts': accounts,
            **stats,
        }
