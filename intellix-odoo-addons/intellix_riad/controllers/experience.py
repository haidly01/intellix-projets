# -*- coding: utf-8 -*-
"""Webhook n8n / canaux OTA — même pattern que doorway_messaging + Léa."""

import json
import logging

from odoo import http
from odoo.http import request
from werkzeug.wrappers import Response

_logger = logging.getLogger(__name__)


def _json(payload, status=200):
    return Response(
        json.dumps(payload),
        status=status,
        mimetype="application/json",
    )


class IntellixRiadExperienceController(http.Controller):
    def _authorized(self):
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_riad.experience_webhook_token")
            or ""
        ).strip()
        if not expected:
            return False
        token = (
            request.httprequest.headers.get("X-Riad-Experience-Token")
            or request.params.get("token")
            or ""
        )
        return token == expected

    def _establishment(self, payload):
        """Isolation stricte : establishment_id ou property_id obligatoire.

        Ne jamais retomber sur « le premier agent actif » (fuite inter-lieux).
        """
        Estab = request.env["intellix.riad.establishment"].sudo()
        estab_id = payload.get("establishment_id")
        if estab_id:
            estab = Estab.browse(int(estab_id)).exists()
            return estab if estab else Estab.browse()
        prop_id = payload.get("property_id")
        if prop_id:
            return Estab.search([("property_id", "=", int(prop_id))], limit=1)
        channex_uuid = (payload.get("channex_property_id") or "").strip()
        if channex_uuid:
            mapping = (
                request.env["coins.channex.mapping"]
                .sudo()
                .search(
                    [
                        ("kind", "=", "property"),
                        ("channex_id", "=", channex_uuid),
                    ],
                    limit=1,
                )
            )
            if mapping and mapping.property_id:
                return Estab.search(
                    [("property_id", "=", mapping.property_id.id)], limit=1
                )
        return Estab.browse()

    @http.route(
        "/intellix_riad/experience/inbound",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def inbound(self, **kw):
        if not self._authorized():
            return _json({"success": False, "error": "unauthorized"}, 401)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            payload = kw or {}
        estab = self._establishment(payload)
        if not estab:
            return _json({"success": False, "error": "no_establishment"}, 404)
        agent = request.env["intellix.riad.experience.agent"].sudo()
        reply = agent.handle_message(
            estab,
            payload.get("text") or payload.get("message") or "",
            channel=payload.get("channel") or "other",
            guest_name=payload.get("guest_name") or "",
        )
        return _json(
            {
                "success": True,
                "auto": bool(reply),
                "reply": reply or "",
                "escalate": not bool(reply),
            }
        )

    @http.route(
        "/intellix_riad/experience/context",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def context(self, **kw):
        if not self._authorized():
            return _json({"success": False, "error": "unauthorized"}, 401)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            payload = kw or {}
        estab = self._establishment(payload)
        if not estab:
            return _json({"success": False, "error": "no_establishment"}, 404)
        agent = request.env["intellix.riad.experience.agent"].sudo()
        from odoo import fields as odoo_fields

        day = odoo_fields.Date.context_today(estab)
        return _json(
            {
                "success": True,
                "establishment": estab.name,
                "availability": agent._availability_lines(estab, day),
                "practical": agent._practical_reply(estab) or "",
                "wellness": agent._wellness_reply(estab),
            }
        )
