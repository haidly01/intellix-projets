# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RenovationMetaLeadgenWebhookController(http.Controller):

    @http.route(
        "/webhook/meta/leads",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def meta_leads_verify(self, **kwargs):
        webhook = request.env["renovation.meta.leadgen.webhook"].sudo()
        token = webhook._get_verify_token()
        mode = kwargs.get("hub.mode")
        challenge = kwargs.get("hub.challenge")
        verify = kwargs.get("hub.verify_token")
        if mode == "subscribe" and verify == token:
            return request.make_response(
                challenge or "",
                headers=[("Content-Type", "text/plain")],
            )
        _logger.warning("Meta leadgen verify failed (mode=%s)", mode)
        return request.make_response("Forbidden", status=403)

    @http.route(
        "/webhook/meta/leads",
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def meta_leads_post(self, **kwargs):
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            _logger.warning("Meta leadgen webhook: invalid JSON")
            return request.make_response("Bad JSON", status=400)

        webhook = request.env["renovation.meta.leadgen.webhook"].sudo()
        results = []
        leadgen_events = []

        for entry in body.get("entry") or []:
            for change in entry.get("changes") or []:
                if change.get("field") == "leadgen":
                    leadgen_events.append(change.get("value") or {})

        if leadgen_events:
            for change_value in leadgen_events:
                try:
                    result, _status = webhook.process_leadgen_event(
                        body, change_value=change_value
                    )
                    results.append(result)
                except Exception:
                    _logger.exception(
                        "Meta leadgen event failed (leadgen_id=%s)",
                        change_value.get("leadgen_id"),
                    )
        else:
            try:
                result, _status = webhook.process_leadgen_event(body)
                results.append(result)
            except Exception:
                _logger.exception("Meta leadgen webhook processing failed")
                return request.make_response({ok: false}, status=500)

        return request.make_response(
            json.dumps({"ok": True, "results": results}),
            headers=[("Content-Type", "application/json")],
        )
