# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class JasonThomasSyncController(http.Controller):

    def _check_api_key(self):
        key = (
            request.httprequest.headers.get('X-IntelliX-Key')
            or request.httprequest.headers.get('X-API-Key')
            or ''
        ).strip()
        expected = request.env['ir.config_parameter'].sudo().get_param('jt.sync.api_key', '')
        return key and expected and key == expected

    @http.route(
        '/doorway/api/jason-thomas/sync-cookies',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def sync_cookies(self, **kwargs):
        if not self._check_api_key():
            return request.make_json_response({'ok': False, 'error': 'unauthorized'}, status=401)

        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return request.make_json_response({'ok': False, 'error': 'invalid_json'}, status=400)

        portail_id = payload.get('portail_id')
        if not portail_id:
            return request.make_json_response({'ok': False, 'error': 'missing_portail_id'}, status=400)

        try:
            record = request.env['jt.sync.cookie'].sudo().upsert_from_payload(payload)
        except Exception as exc:
            _logger.exception('JT sync cookies failed')
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=400)

        return request.make_json_response({
            'ok': True,
            'portail_id': portail_id,
            'nb_cookies': record.nb_cookies,
            'captured_at': record.captured_at.isoformat() if record.captured_at else None,
        })

    @http.route(
        '/doorway/api/jason-thomas/sync-status',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def sync_status(self, **kwargs):
        if not self._check_api_key():
            return request.make_json_response({'ok': False, 'error': 'unauthorized'}, status=401)

        cookies = request.env['jt.sync.cookie'].sudo().search([])
        portails = [{
            'portail_id': c.portail_id,
            'portail_nom': c.portail_nom,
            'nb_cookies': c.nb_cookies,
            'captured_at': c.captured_at.isoformat() if c.captured_at else None,
        } for c in cookies]
        return request.make_json_response({'ok': True, 'portails': portails})

    @http.route(
        '/doorway/api/jason-thomas/sync-polices',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def sync_polices(self, **kwargs):
        """Reçoit un export Assomption (XLS) extrait dans le navigateur de Jason."""
        if not self._check_api_key():
            return request.make_json_response({'ok': False, 'error': 'unauthorized'}, status=401)

        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return request.make_json_response({'ok': False, 'error': 'invalid_json'}, status=400)

        fmt = (payload.get('format') or 'xls_base64').strip().lower()
        if fmt not in ('xls_base64', 'xls'):
            return request.make_json_response(
                {'ok': False, 'error': f'unsupported_format:{fmt}'},
                status=400,
            )

        try:
            result = request.env['jt.sync.import'].sudo().import_assomption_xls_payload(payload)
        except Exception as exc:
            _logger.exception('JT sync polices failed')
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=400)

        return request.make_json_response(result)
