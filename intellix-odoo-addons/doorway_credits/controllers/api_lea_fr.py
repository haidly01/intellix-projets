# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class LeaFrApiController(http.Controller):
    """Léa FR — recrutement artisans partenaires MaRénoFacile (B2B).
    Un artisan qualifié (RDV pris) => lead assigné à Karine + activité RDV MaRénoFacile."""

    def _tenant_from_key(self, tenant_api_key):
        return request.env["doorway.tenant"].get_tenant_by_api_key(tenant_api_key)

    @http.route(
        "/doorway/api/lea-fr/call-ended",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.lea_fr_service import (
            LeaFrService,
        )

        crm = LeaFrService(request.env(su=True)).process_call_ended(payload)
        return {"success": True, "crm": crm}

    @http.route(
        "/doorway/api/lea-fr/call-recording",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_recording(self, tenant_api_key, call_sid, recording_url, **payload):
        """Enregistrement Léa FR prêt — upsert doorway.call.log."""
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        company_id = tenant.company_id.id if tenant else False
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            log_rec = VicidialService(request.env(su=True)).upsert_sofia_call_recording(
                {
                    **payload,
                    "call_sid": call_sid,
                    "recording_url": recording_url,
                    "campaign": payload.get("campaign") or "DW_LEAFR",
                    "agent_id": payload.get("agent_id") or "lea-fr",
                },
                company_id=company_id,
                fast=True,
            )
            return {
                "success": True,
                "call_log_id": log_rec.id if log_rec else False,
            }
        except Exception as exc:
            _logger.exception("Léa FR call recording upsert failed: %s", exc)
            return {"success": False, "error": str(exc)}
