import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RenovationRetellWebhookController(http.Controller):
    def _handle_agent_ia_crm_webhook(self, pipeline_key):
        raw_bytes = request.httprequest.data or b"{}"
        raw_body = raw_bytes.decode("utf-8", errors="replace")

        signature = request.httprequest.headers.get("X-Retell-Signature")
        webhook = request.env["renovation.retell.webhook"].sudo()

        if signature:
            if not webhook.verify_retell_signature(raw_body, signature):
                _logger.warning("Retell webhook: signature invalide.")
                return request.make_response(
                    "Unauthorized",
                    status=401,
                    headers=[("Content-Type", "text/plain")],
                )
        else:
            try:
                payload_probe = json.loads(raw_body) if raw_body.strip() else {}
            except json.JSONDecodeError:
                payload_probe = {}
            if not webhook._check_optional_token(payload_probe, pipeline_key):
                return request.make_response(
                    "Unauthorized",
                    status=401,
                    headers=[("Content-Type", "text/plain")],
                )

        try:
            payload = json.loads(raw_body) if raw_body.strip() else {}
        except json.JSONDecodeError:
            payload = {}

        try:
            result = webhook.process_webhook_payload(payload, pipeline_key)
        except Exception:
            _logger.exception("Webhook Agent IA CRM failed (%s)", pipeline_key)
            return request.make_response(
                "Internal Server Error",
                status=500,
                headers=[("Content-Type", "text/plain")],
            )

        inbound_response = result.get("inbound_response")
        if inbound_response:
            return request.make_json_response(inbound_response, status=200)

        return request.make_response("", status=204)

    @http.route(
        "/renovation/retell/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def retell_webhook_renovation(self, **kwargs):
        return self._handle_agent_ia_crm_webhook("renovation")

    @http.route(
        "/marketing/retell/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def retell_webhook_marketing(self, **kwargs):
        return self._handle_agent_ia_crm_webhook("marketing")

    @http.route(
        "/immobilier/agents/webhook/crm",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def agent_ia_webhook_immobilier(self, **kwargs):
        return self._handle_agent_ia_crm_webhook("immobilier")

    @http.route(
        "/renovation/agents/webhook/crm",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def agent_ia_webhook_renovation(self, **kwargs):
        return self._handle_agent_ia_crm_webhook("renovation")

    @http.route(
        "/marketing/agents/webhook/crm",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def agent_ia_webhook_marketing(self, **kwargs):
        return self._handle_agent_ia_crm_webhook("marketing")

    @http.route(
        "/api/agents/webhook/crm",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def agent_ia_webhook_crm_api(self, **kwargs):
        raw = request.httprequest.data or b"{}"
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            payload = {}
        pipeline_key = (
            payload.get("pipeline")
            or payload.get("pipeline_key")
            or "immobilier"
        )
        return self._handle_agent_ia_crm_webhook(pipeline_key)
