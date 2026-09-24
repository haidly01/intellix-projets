# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DoorwayWaLogController(http.Controller):
    def _expected_token(self):
        return (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_messaging.wa_log_webhook_token", "")
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

    @staticmethod
    def _normalize_phone(phone):
        digits = re.sub(r"[^\d+]", "", phone or "")
        if digits.startswith("00"):
            return "+" + digits[2:]
        return digits

    def _find_lead(self, phone, lead_id=None):
        Lead = request.env["crm.lead"].sudo()
        if lead_id:
            try:
                lead = Lead.browse(int(lead_id))
                if lead.exists():
                    return lead
            except (TypeError, ValueError):
                pass
        norm = self._normalize_phone(phone)
        if not norm or len(norm) < 8:
            return Lead.browse()
        tail = norm[-10:]
        try:
            return Lead.search(
                ["|", ("phone", "ilike", tail), ("mobile", "ilike", tail)],
                limit=1,
            )
        except Exception:
            _logger.exception("WA log: recherche lead par telephone")
            return Lead.browse()

    @http.route(
        "/doorway/api/wa/log",
        auth="public",
        csrf=False,
        methods=["POST"],
        type="http",
    )
    def wa_log(self, **kwargs):
        expected = self._expected_token()
        if not expected or self._provided_token() != expected:
            return request.make_response(
                json.dumps({"error": "unauthorized"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )
        data = self._json_body()
        phone = data.get("phone") or ""
        body = data.get("body") or data.get("reply_body") or ""
        direction = data.get("direction") or "inbound"
        statut = data.get("statut") or ("received" if direction == "inbound" else "sent")
        provider = data.get("provider") or "twilio"
        lead = self._find_lead(phone, data.get("lead_id"))
        payload = data.get("payload")
        if payload is not None and not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)
        log = request.env["doorway.wa.log"].sudo().create(
            {
                "lead_id": lead.id if lead else False,
                "partner_id": lead.partner_id.id if lead and lead.partner_id else False,
                "direction": direction,
                "phone": phone,
                "body": body,
                "statut": statut,
                "provider": provider,
                "external_sid": data.get("external_sid") or data.get("reply_sid") or "",
                "payload_json": payload or False,
            }
        )
        if lead and direction == "inbound" and body:
            lead.message_post(
                body="WhatsApp entrant : %s" % (body[:500]),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        return request.make_response(
            json.dumps({"ok": True, "log_id": log.id}),
            headers=[("Content-Type", "application/json")],
            status=200,
        )
