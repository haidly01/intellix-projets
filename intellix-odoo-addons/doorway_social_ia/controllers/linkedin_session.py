# -*- coding: utf-8 -*-
"""Ingest public des sessions LinkedIn (extension Chrome), comme Jason Thomas."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

UPSTREAM = "http://127.0.0.1:43147/api/linkedin/session"
PARAM_KEY = "doorway.linkedin.sync.api_key"


class DoorwayLinkedinSessionIngest(http.Controller):
    def _cors_headers(self):
        origin = request.httprequest.headers.get("Origin") or ""
        headers = [
            ("Content-Type", "application/json"),
        ]
        if origin.startswith("chrome-extension://"):
            headers.extend(
                [
                    ("Access-Control-Allow-Origin", origin),
                    ("Access-Control-Allow-Headers", "content-type, x-intellix-key, x-api-key"),
                    ("Access-Control-Allow-Methods", "POST, OPTIONS"),
                ]
            )
        return headers

    def _check_api_key(self):
        key = (
            request.httprequest.headers.get("X-IntelliX-Key")
            or request.httprequest.headers.get("X-API-Key")
            or ""
        ).strip()
        expected = (
            request.env["ir.config_parameter"].sudo().get_param(PARAM_KEY, "") or ""
        ).strip()
        return bool(key and expected and key == expected)

    def _json(self, payload, status=200):
        resp = request.make_json_response(payload, status=status)
        for name, value in self._cors_headers():
            if name.lower() == "content-type":
                continue
            resp.headers[name] = value
        return resp

    @http.route(
        "/doorway/api/linkedin/session",
        type="http",
        auth="public",
        csrf=False,
        methods=["POST", "OPTIONS"],
    )
    def ingest(self, **_kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=self._cors_headers())
        if not self._check_api_key():
            return self._json({"ok": False, "error": "unauthorized"}, status=401)
        raw = request.httprequest.get_data() or b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "error": "json invalide"}, status=400)
        account = payload.get("account") or "?"
        req = Request(
            UPSTREAM,
            data=raw,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
                status = resp.status
        except HTTPError as err:
            body = json.loads(err.read().decode("utf-8") or "{}") if err.fp else {"error": err.reason}
            status = err.code
        except URLError as err:
            _logger.warning("linkedin session ingest: node injoignable (%s)", err)
            return self._json(
                {"ok": False, "error": "tableau de bord LinkedIn indisponible"},
                status=503,
            )
        _logger.info(
            "linkedin session ingest account=%s count=%s ok=%s",
            account,
            body.get("count"),
            body.get("ok"),
        )
        return self._json(body, status=status)
