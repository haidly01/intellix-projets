# -*- coding: utf-8 -*-
import json
import logging
import os

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Doorway-Canva-Key",
}


class DoorwayCanvaMcp(http.Controller):

    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload),
            headers={**CORS_HEADERS, "Content-Type": "application/json"},
            status=status,
        )

    def _parse_body(self):
        raw = request.httprequest.get_data(as_text=True) or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _check_api_key(self, body):
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_social_ia.canva_api_key")
            or ""
        ).strip()
        if not expected:
            return True
        provided = (
            request.httprequest.headers.get("X-Doorway-Canva-Key")
            or body.get("api_key")
            or ""
        ).strip()
        return provided == expected

    @http.route(
        "/doorway/canva/mcp",
        type="http",
        auth="public",
        csrf=False,
        methods=["OPTIONS"],
    )
    def canva_mcp_options(self, **kwargs):
        return request.make_response("", headers=CORS_HEADERS)

    @http.route(
        "/doorway/canva/mcp",
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def canva_mcp(self, **kwargs):
        body = self._parse_body()
        if not self._check_api_key(body):
            return self._json_response({"error_code": "unauthorized"}, status=401)

        action = body.get("action")
        service = request.env["doorway.social.canva.service"].sudo()

        try:
            if action == "create_design":
                result = service.handle_create_design(body)
            elif action == "publish_content":
                result = service.handle_publish_content(body)
            elif action == "get_publish_config":
                result = service.handle_get_publish_config()
            else:
                return self._json_response(
                    {"error_code": "unknown_action"},
                    status=400,
                )
        except Exception as exc:  # noqa: BLE001
            from odoo.addons.doorway_social_ia.models.doorway_social_canva_service import (
                CanvaMcpError,
            )

            if isinstance(exc, CanvaMcpError):
                _logger.warning("Canva MCP %s: %s", action, exc.error_code)
                return self._json_response(
                    {"error_code": exc.error_code},
                    status=exc.http_status,
                )
            _logger.exception("Canva MCP error (%s): %s", action, exc)
            return self._json_response({"error_code": "server_error"}, status=500)

        return self._json_response(result)

    def _serve_download(self, filename, mimetype, download_name=None):
        allowed = {
            "app.js": ("app.js", "application/javascript"),
            "intellix-canva-messages_en-US.json": (
                "intellix-canva-messages_en-US.json",
                "application/json",
            ),
        }
        if filename not in allowed:
            return request.not_found()
        disk_name, content_type = allowed[filename]
        module_path = get_module_path("doorway_social_ia")
        file_path = os.path.join(module_path, "static", "download", disk_name)
        if not os.path.isfile(file_path):
            return request.not_found()
        with open(file_path, "rb") as handle:
            data = handle.read()
        name = download_name or disk_name
        return request.make_response(
            data,
            headers=[
                ("Content-Type", content_type),
                ("Content-Disposition", f'attachment; filename="{name}"'),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )

    @http.route(
        "/doorway/canva/download/app.js",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def download_canva_app_js(self, **kwargs):
        return self._serve_download("app.js", "application/javascript")

    @http.route(
        "/doorway/canva/download/intellix-canva-messages_en-US.json",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def download_canva_translations(self, **kwargs):
        return self._serve_download(
            "intellix-canva-messages_en-US.json", "application/json"
        )
