# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class IntellixSupportCursorController(http.Controller):
    def _expected_token(self):
        return (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_support.api_token", "")
            .strip()
        )

    def _provided_token(self):
        hdr = request.httprequest.headers.get("X-Doorway-Token")
        if hdr:
            return hdr.strip()
        return (request.httprequest.headers.get("X-Doorway-Key") or "").strip()

    def _json_body(self):
        raw = request.httprequest.get_data(as_text=True) or ""
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {}

    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

    def _auth_ok(self):
        expected = self._expected_token()
        if not expected:
            return False
        return self._provided_token() == expected

    @http.route(
        "/doorway/support/cursor/dispatch",
        auth="public",
        csrf=False,
        methods=["POST"],
        type="http",
    )
    def cursor_dispatch(self, **kwargs):
        """Dispatch analyse Cursor pour un ticket (token API support)."""
        if not self._auth_ok():
            return self._json_response({"error": "unauthorized"}, 401)

        data = self._json_body()
        ticket_id = data.get("ticket_id")
        try:
            ticket_id = int(ticket_id)
        except (TypeError, ValueError):
            return self._json_response({"error": "ticket_id required"}, 400)

        ticket = request.env["intellix.support.ticket"].sudo().browse(ticket_id)
        if not ticket.exists():
            return self._json_response({"error": "not found"}, 404)

        proposal = request.env["intellix.support.fix.proposal"].sudo().browse()
        proposal_id = data.get("proposal_id")
        if proposal_id:
            try:
                proposal = request.env["intellix.support.fix.proposal"].sudo().browse(
                    int(proposal_id)
                )
                if not proposal.exists() or proposal.ticket_id != ticket:
                    proposal = request.env["intellix.support.fix.proposal"].sudo().browse()
            except (TypeError, ValueError):
                pass

        bridge = request.env["intellix.support.cursor.bridge"].sudo()
        try:
            info = bridge.dispatch_ticket_analysis(
                ticket,
                proposal=proposal if proposal else None,
                source=data.get("source") or "api",
            )
        except (UserError, AccessError) as err:
            return self._json_response({"error": str(err)}, 400)

        return self._json_response({"ok": True, **info})
