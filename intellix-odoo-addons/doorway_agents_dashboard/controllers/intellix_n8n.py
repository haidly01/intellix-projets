# -*- coding: utf-8 -*-
"""API Intellix pour workflows n8n (tags CRM, logs, prospection)."""
import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.doorway_agents_dashboard.services.config_loader import get_secret

_logger = logging.getLogger(__name__)

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Doorway-Key",
}


class IntellixN8nController(http.Controller):
    def _check_key(self):
        expected = get_secret(
            request.env,
            "DOORWAY_AGENTS_WEBHOOK_KEY",
            "doorway_agents_dashboard.webhook_token",
        )
        provided = request.httprequest.headers.get("X-Doorway-Key") or ""
        return expected and provided == expected

    def _body(self):
        raw = request.httprequest.get_data(as_text=True) or ""
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return None

    def _tag(self, name):
        Tag = request.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag

    @http.route(
        "/api/intellix/n8n/crm",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def n8n_crm(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        if not self._check_key():
            return request.make_json_response(
                {"status": "error", "message": "Non autorisé"}, status=401, headers=CORS
            )
        data = self._body()
        if data is None:
            return request.make_json_response(
                {"status": "error", "message": "JSON invalide"}, status=400, headers=CORS
            )

        action = data.get("action")
        Lead = request.env["crm.lead"].sudo()

        if action == "get_lead":
            lead = Lead.browse(int(data.get("lead_id") or 0))
            if not lead.exists():
                return request.make_json_response(
                    {"status": "error", "message": "Lead introuvable"}, status=404, headers=CORS
                )
            prenom = (lead.contact_name or lead.name or "").split()[0]
            return request.make_json_response(
                {
                    "status": "ok",
                    "lead_id": lead.id,
                    "prenom": prenom,
                    "ville": lead.city or "",
                    "nom": lead.contact_name or lead.name,
                    "nom_centre": lead.partner_name or lead.name,
                    "phone": lead.phone or lead.mobile or "",
                    "email": lead.email_from or "",
                    "partner_id": lead.partner_id.id if lead.partner_id else False,
                    "nb_agents_estime": int(getattr(lead, "x_nb_agents_estime", 0) or 0),
                    "tag_names": lead.tag_ids.mapped("name"),
                },
                headers=CORS,
            )

        lead = Lead.browse(int(data.get("lead_id") or 0))
        if not lead.exists():
            return request.make_json_response(
                {"status": "error", "message": "Lead introuvable"}, status=404, headers=CORS
            )

        if action == "tag":
            tag_name = data.get("tag_name") or data.get("tag")
            if tag_name:
                lead.write({"tag_ids": [(4, self._tag(tag_name).id)]})
            return request.make_json_response({"status": "ok", "tags": lead.tag_ids.mapped("name")}, headers=CORS)

        if action == "untag":
            tag_name = data.get("tag_name") or data.get("tag")
            tag = request.env["crm.tag"].sudo().search([("name", "=", tag_name)], limit=1)
            if tag:
                lead.write({"tag_ids": [(3, tag.id)]})
            return request.make_json_response({"status": "ok"}, headers=CORS)

        if action == "log":
            msg = data.get("message") or data.get("body") or ""
            if msg:
                lead.message_post(body=msg, message_type="comment", subtype_xmlid="mail.mt_note")
            return request.make_json_response({"status": "ok"}, headers=CORS)

        if action == "has_reply":
            msgs = lead.message_ids.filtered(
                lambda m: m.message_type == "email" and m.author_id != lead.user_id.partner_id
            )
            return request.make_json_response(
                {"status": "ok", "has_reply": bool(msgs), "count": len(msgs)},
                headers=CORS,
            )

        return request.make_json_response(
            {"status": "error", "message": "action inconnue"}, status=400, headers=CORS
        )
