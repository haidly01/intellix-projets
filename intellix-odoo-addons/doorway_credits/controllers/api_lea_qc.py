# -*- coding: utf-8 -*-
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class LeaQcApiController(http.Controller):
    def _tenant_from_key(self, tenant_api_key):
        return request.env["doorway.tenant"].get_tenant_by_api_key(tenant_api_key)

    @http.route(
        "/doorway/api/lea-qc/contacts",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def list_contacts(self, tenant_api_key, limit=50, **kwargs):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        Cat = request.env["res.partner.category"].sudo()
        brut = Cat.search([("name", "=", "B2C Brut")], limit=1)
        appelle = Cat.search([("name", "=", "Appelé Léa")], limit=1)
        domain = [("phone", "!=", False)]
        if brut:
            domain.append(("category_id", "in", [brut.id]))
        if appelle:
            domain.append(("category_id", "not in", [appelle.id]))
        partners = request.env["res.partner"].sudo().search(domain, limit=int(limit or 50))
        return {
            "success": True,
            "contacts": [
                {
                    "id": p.id,
                    "name": p.name,
                    "phone": p.phone or p.mobile,
                    "prenom": (p.name or "").split()[0] if p.name else "",
                }
                for p in partners
            ],
        }

    @http.route(
        "/doorway/api/lea-qc/call-ended",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_service import (
            LeaQcService,
        )

        crm = LeaQcService(request.env(su=True)).process_post_call(payload)
        return {"success": True, "crm": crm}

    @http.route(
        "/doorway/api/lea-qc/qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_service import (
            LeaQcService,
        )

        crm = LeaQcService(request.env(su=True)).process_qualified(payload)
        return {"success": True, "crm": crm}

    @http.route(
        "/doorway/api/lea-qc/non-qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def non_qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_service import (
            LeaQcService,
        )

        crm = LeaQcService(request.env(su=True)).process_non_qualified(payload)
        return {"success": True, "crm": crm}

    @http.route(
        "/doorway/api/lea-qc/call-recording",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_recording(self, tenant_api_key, call_sid, recording_url, **payload):
        """Enregistrement Léa-QC prêt — upsert doorway.call.log (réponse rapide)."""
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        company_id = tenant.company_id.id if tenant else False
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            patch = {
                **payload,
                "call_sid": call_sid,
                "recording_url": recording_url,
                "campaign": payload.get("campaign") or "DW_QCB2C",
                "agent_id": payload.get("agent_id") or "lea-qc-2026",
            }
            log_rec = VicidialService(request.env(su=True)).upsert_sofia_call_recording(
                patch,
                company_id=company_id,
                fast=True,
            )
            return {
                "success": True,
                "call_log_id": log_rec.id if log_rec else False,
            }
        except Exception as exc:
            _logger.exception("Léa-QC call recording upsert failed: %s", exc)
            return {"success": False, "error": str(exc)}

    @http.route(
        "/doorway/api/lea-qc/dial",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def dial(self, tenant_api_key, telephone, **payload):
        """Outbound VICIdial — Africa-Con trunk, campagne DW_QCB2C (ratio dial primaire)."""
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key", "ok": False}
        digits = re.sub(r"\D", "", telephone or "")
        if len(digits) == 10:
            digits = "1" + digits
        if not digits:
            return {"success": False, "error": "telephone_required", "ok": False}
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            svc = VicidialService(request.env)
            campaign = payload.get("campaign") or "DW_QCB2C"
            result = svc.call_out_number(
                digits,
                campaign=campaign,
                phone_code="1",
            )
            return {
                "success": True,
                "ok": bool(result.get("ok")),
                "telephone": telephone,
                "provider": "vicidial",
                "campaign": campaign,
                "raw": result,
            }
        except Exception as exc:
            _logger.exception("Léa QC dial failed: %s", exc)
            return {"success": False, "ok": False, "error": str(exc)}
