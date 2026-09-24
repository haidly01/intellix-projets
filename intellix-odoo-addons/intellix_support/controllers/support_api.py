# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class IntellixSupportApiController(http.Controller):
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
        "/doorway/api/support/ticket",
        auth="public",
        csrf=False,
        methods=["POST"],
        type="http",
    )
    def create_ticket(self, **kwargs):
        if not self._auth_ok():
            return self._json_response({"error": "unauthorized"}, 401)

        data = self._json_body()
        subject = (data.get("subject") or "").strip()
        if not subject:
            return self._json_response({"error": "subject required"}, 400)

        Ticket = request.env["intellix.support.ticket"].sudo()
        Category = request.env["intellix.support.category"].sudo()
        Partner = request.env["res.partner"].sudo()

        partner = Partner.browse()
        partner_id = data.get("partner_id")
        if partner_id:
            partner = Partner.browse(int(partner_id))
            if not partner.exists():
                partner = Partner.browse()

        category = Category.browse()
        category_code = (data.get("category_code") or "").strip()
        if category_code:
            category = Category.search([("code", "=", category_code)], limit=1)

        vals = {
            "subject": subject,
            "description": data.get("description") or "",
            "partner_id": partner.id if partner else False,
            "category_id": category.id if category else False,
            "user_id": False,
        }
        if data.get("anydesk_id"):
            vals["anydesk_id"] = str(data["anydesk_id"]).strip()
        if data.get("contact_user_id"):
            try:
                vals["contact_user_id"] = int(data["contact_user_id"])
            except (TypeError, ValueError):
                pass

        ticket = Ticket.create(vals)
        if data.get("run_diagnostic"):
            request.env["intellix.support.diagnostic.engine"].sudo().run_for_ticket(ticket)

        return self._json_response(
            {
                "ok": True,
                "ticket_id": ticket.id,
                "name": ticket.name,
                "side_origin": ticket.side_origin,
            }
        )

    @http.route(
        "/doorway/api/support/ticket/<int:ticket_id>/diagnostic",
        auth="public",
        csrf=False,
        methods=["POST"],
        type="http",
    )
    def run_diagnostic(self, ticket_id, **kwargs):
        if not self._auth_ok():
            return self._json_response({"error": "unauthorized"}, 401)

        ticket = request.env["intellix.support.ticket"].sudo().browse(ticket_id)
        if not ticket.exists():
            return self._json_response({"error": "not found"}, 404)

        diagnostic = (
            request.env["intellix.support.diagnostic.engine"]
            .sudo()
            .run_for_ticket(ticket)
        )
        return self._json_response(
            {
                "ok": True,
                "diagnostic_id": diagnostic.id,
                "side_origin": diagnostic.side_origin,
                "checks_passed": diagnostic.checks_passed,
                "checks_warning": diagnostic.checks_warning,
                "checks_failed": diagnostic.checks_failed,
            }
        )
