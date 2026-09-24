import json
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

PORTAIL_SELECTION = [
    ('ia_secureweb', 'iA Secureweb Inalco'),
    ('ago_ia', 'AGO iA Excellence'),
    ('assomption', 'Assomption — compte 1 (6TZ2)'),
    ('assomption_2', 'Assomption — compte 2 (A0YX)'),
]


class JTSyncCookie(models.Model):
    _name = 'jt.sync.cookie'
    _description = 'Cookies portail — sync Jason Thomas'
    _rec_name = 'portail_id'

    portail_id = fields.Selection(PORTAIL_SELECTION, string='Portail', required=True, index=True)
    portail_nom = fields.Char('Nom portail')
    domaine = fields.Char('Domaine')
    cookies_json = fields.Text('Cookies (JSON)', required=True)
    captured_at = fields.Datetime('Capturé le', required=True)
    url_source = fields.Char('URL source')
    nb_cookies = fields.Integer('Nb cookies', compute='_compute_nb_cookies')

    _sql_constraints = [
        ('portail_unique', 'unique(portail_id)', 'Un seul enregistrement par portail.'),
    ]

    @api.depends('cookies_json')
    def _compute_nb_cookies(self):
        for record in self:
            try:
                data = json.loads(record.cookies_json or '[]')
                record.nb_cookies = len(data) if isinstance(data, list) else 0
            except json.JSONDecodeError:
                record.nb_cookies = 0

    @api.model
    def upsert_from_payload(self, payload: dict):
        portail_id = payload.get('portail_id')
        if portail_id not in dict(PORTAIL_SELECTION):
            raise ValidationError(f'Portail inconnu: {portail_id}')

        cookies = payload.get('cookies') or []
        captured_raw = payload.get('capturé_le') or payload.get('capture_le')
        if captured_raw:
            # Extension envoie ISO (…T…Z) ; Odoo Datetime attend 'YYYY-MM-DD HH:MM:SS'
            raw = str(captured_raw).strip().replace('T', ' ').replace('Z', '')
            if '.' in raw:
                raw = raw.split('.', 1)[0]
            try:
                captured = fields.Datetime.to_datetime(raw)
            except Exception:
                captured = fields.Datetime.now()
        else:
            captured = fields.Datetime.now()
        vals = {
            'portail_nom': payload.get('portail_nom'),
            'domaine': payload.get('domaine'),
            'cookies_json': json.dumps(cookies, ensure_ascii=False),
            'captured_at': captured,
            'url_source': payload.get('url_source'),
        }
        existing = self.search([('portail_id', '=', portail_id)], limit=1)
        if existing:
            existing.write(vals)
            record = existing
        else:
            record = self.create({'portail_id': portail_id, **vals})

        self._write_cookies_file()
        _logger.info('JT sync cookies updated for %s (%s cookies)', portail_id, len(cookies))
        return record

    @api.model
    def _cookies_file_path(self):
        icp = self.env['ir.config_parameter'].sudo()
        return icp.get_param(
            'jt.sync.cookies_path',
            '/opt/intellix/jason_sync/cookies_session.json',
        )

    @api.model
    def _write_cookies_file(self):
        """Exporte vers le fichier lu par sync_nocturne.py sur le serveur."""
        path = self._cookies_file_path()
        if not path:
            return
        export = {}
        for record in self.search([]):
            try:
                cookies = json.loads(record.cookies_json or '[]')
            except json.JSONDecodeError:
                cookies = []
            export[record.portail_id] = {
                'portail_id': record.portail_id,
                'portail_nom': record.portail_nom,
                'domaine': record.domaine,
                'cookies': cookies,
                'capturé_le': fields.Datetime.to_string(record.captured_at),
                'url_source': record.url_source,
            }
        try:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(export, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            _logger.warning('Impossible d\'écrire %s: %s', path, exc)

    @api.model
    def export_all_as_dict(self):
        result = {}
        for record in self.search([]):
            try:
                cookies = json.loads(record.cookies_json or '[]')
            except json.JSONDecodeError:
                cookies = []
            result[record.portail_id] = {
                'portail_id': record.portail_id,
                'cookies': cookies,
                'capturé_le': fields.Datetime.to_string(record.captured_at),
            }
        return result
