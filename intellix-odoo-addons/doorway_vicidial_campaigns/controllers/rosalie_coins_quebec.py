# -*- coding: utf-8 -*-
"""Webhook AGI Rosalie — /doorway/api/rosalie-coins-quebec/*

Écrit uniquement dans coins.quebec.partenariat (ou voyageur si dit).
Jamais crm.lead Coins Marocain / Driven / Sales.
"""
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RosalieCoinsQuebecApiController(http.Controller):
    def _tenant_from_key(self, tenant_api_key):
        Tenant = request.env["doorway.tenant"].sudo()
        return Tenant.get_tenant_by_api_key(tenant_api_key)

    def _router(self):
        from odoo.addons.doorway_vicidial_campaigns.services.campaign_crm_router import (
            CampaignCrmRouter,
        )

        return CampaignCrmRouter(request.env(su=True))

    def _payload(self, tenant_api_key, payload):
        data = dict(payload or {})
        data.setdefault("campaign", "CQMTG01")
        data.setdefault("odoo_slug", "rosalie-coins-quebec")
        data.setdefault("agent_id", "agent_rosalie_cq")
        return data

    @http.route(
        "/doorway/api/rosalie-coins-quebec/call-ended",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        data = self._payload(tenant_api_key, payload)
        result = self._router().route_rosalie(data, dry_run=bool(data.get("dry_run")))
        return {"success": bool(result.get("ok")), **result}

    @http.route(
        "/doorway/api/rosalie-coins-quebec/qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        data = self._payload(tenant_api_key, payload)
        data["qualified"] = True
        result = self._router().route_rosalie(data, dry_run=bool(data.get("dry_run")))
        return {"success": bool(result.get("ok")), **result}

    @http.route(
        "/doorway/api/rosalie-coins-quebec/non-qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def non_qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        data = self._payload(tenant_api_key, payload)
        data["qualified"] = False
        result = self._router().route_rosalie(data, dry_run=bool(data.get("dry_run")))
        return {"success": bool(result.get("ok")), **result}
