# -*- coding: utf-8 -*-
"""Proxy authentifié vers le dashboard Node (maquette Veille + LinkedIn)."""

import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import http
from odoo.http import request

from . import veille_dash_api

_logger = logging.getLogger(__name__)

UPSTREAM = "http://127.0.0.1:43147"
INJECT = b'<script>window.SOCIAL_API_PREFIX="/doorway/social-dash";</script>'


class DoorwaySocialDashProxy(http.Controller):
    @http.route(
        [
            "/doorway/social-dash",
            "/doorway/social-dash/",
            "/doorway/social-dash/<path:subpath>",
        ],
        type="http",
        auth="user",
        csrf=False,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    def proxy(self, subpath="", **_kwargs):
        path = "/" + (subpath or "")
        if path.startswith("/api/signals") or path.startswith("/api/veille/"):
            handled = veille_dash_api.handle(path, request.httprequest.method)
            if handled is not None:
                return handled

        qs = request.httprequest.query_string
        if isinstance(qs, bytes):
            qs = qs.decode()
        url = UPSTREAM + path
        if qs:
            url = url + "?" + qs

        headers = {}
        ctype = request.httprequest.headers.get("Content-Type")
        if ctype:
            headers["Content-Type"] = ctype
        body = request.httprequest.get_data() or None
        method = request.httprequest.method or "GET"
        if method in ("GET", "HEAD", "OPTIONS"):
            body = None
        req = Request(url, data=body, method=method, headers=headers)
        timeout = 90 if "verify" in path else 20
        try:
            with urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
                status = resp.status
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
        except HTTPError as err:
            payload = err.read() or str(err.reason).encode()
            status = err.code
            content_type = err.headers.get("Content-Type", "text/plain; charset=utf-8")
        except URLError as err:
            _logger.warning("dashboard reseaux-sociaux injoignable: %s", err)
            html = (
                "<!doctype html><meta charset='utf-8'>"
                "<body style='font-family:sans-serif;background:#14161c;color:#e9e7e1;padding:40px'>"
                "<h1>Tableau de bord indisponible</h1>"
                "<p>Le service LinkedIn / veille n’est pas démarré. Réessaie dans un instant.</p>"
                "</body>"
            )
            return request.make_response(
                html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
                status=503,
            )

        if "text/html" in (content_type or "") and INJECT not in payload:
            if b"</head>" in payload:
                payload = payload.replace(b"</head>", INJECT + b"</head>", 1)
            else:
                payload = INJECT + payload

        extra_headers = [("Content-Type", content_type)]
        if "application/zip" in (content_type or ""):
            extra_headers.append(
                ("Content-Disposition", 'attachment; filename="IntelliX-Session-1.4.1.zip"')
            )
        return request.make_response(payload, headers=extra_headers, status=status)
