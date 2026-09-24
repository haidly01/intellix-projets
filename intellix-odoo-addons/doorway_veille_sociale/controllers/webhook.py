# -*- coding: utf-8 -*-
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Doorway-Token",
}


class VeilleWebhookController(http.Controller):
    def _json_response(self, payload, status=200):
        headers = dict(CORS_HEADERS)
        headers["Content-Type"] = "application/json"
        return request.make_response(
            json.dumps(payload), headers=list(headers.items()), status=status
        )

    def _parse_payload(self, kwargs):
        data = dict(kwargs or {})
        try:
            raw = request.httprequest.get_data(as_text=True)
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data.update(parsed)
                elif isinstance(parsed, list) and parsed:
                    data = parsed[0] if isinstance(parsed[0], dict) else data
        except (ValueError, TypeError):
            pass
        return data

    def _check_token(self):
        cfg = request.env["doorway.veille.config"].sudo().get_config()
        configured = cfg.webhook_token or ""
        provided = (
            request.httprequest.headers.get("X-Doorway-Token")
            or request.httprequest.headers.get("X-Doorway-Webhook-Token")
            or ""
        )
        if not configured or not hmac.compare_digest(str(provided), str(configured)):
            return False
        return True

    @http.route(
        "/doorway/veille/webhook",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def receive_signal(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=list(CORS_HEADERS.items()))

        if not self._check_token():
            return self._json_response(
                {"status": "error", "message": "Token invalide ou manquant."},
                401,
            )

        data = self._parse_payload(kwargs)
        if not data:
            return self._json_response(
                {"status": "error", "message": "Corps JSON vide ou invalide."},
                400,
            )

        Signal = request.env["doorway.veille.signal"].sudo()
        try:
            signal = Signal.upsert_from_payload(data)
        except Exception as error:  # noqa: BLE001
            _logger.exception("Webhook veille : échec upsert signal")
            return self._json_response(
                {"status": "error", "message": str(error)},
                500,
            )

        if signal.temperature == "hot" and signal.statut == "en_attente":
            try:
                signal._notify_hot()
            except Exception:  # noqa: BLE001
                _logger.exception("Webhook veille : alerte hot impossible")

        lead_id = False
        # Pas de création CRM automatique à la réception : triage humain
        # (ignorer / répondre / accepter / créer lead) avant opportunité.

        return self._json_response(
            {
                "status": "ok",
                "signal_id": signal.id,
                "signal_id_externe": signal.signal_id_externe or False,
                "lead_id": lead_id or False,
            }
        )
