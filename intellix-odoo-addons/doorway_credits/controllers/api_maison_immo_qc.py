# -*- coding: utf-8 -*-
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MaisonImmoQcApiController(http.Controller):
    def _tenant_from_key(self, tenant_api_key):
        return request.env["doorway.tenant"].get_tenant_by_api_key(tenant_api_key)

    @http.route(
        "/doorway/api/maison-immo-qc/call-ended",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.maison_immo_qc_service import (
            MaisonImmoQcService,
        )

        crm = MaisonImmoQcService(request.env(su=True)).process_call_ended(payload)
        call_log_id = False
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            log_rec = VicidialService(request.env(su=True)).upsert_call_from_pipeline(
                {
                    **payload,
                    "campaign": payload.get("campaign") or "MR_IMMO_QC",
                    "lead_ganador": payload.get("qualified"),
                    "etat_final": payload.get("statut") or payload.get("crm_action"),
                },
                company_id=tenant.company_id.id if tenant else False,
            )
            if log_rec:
                call_log_id = log_rec.id
        except Exception as exc:
            _logger.exception("Maison MR QC call log upsert failed: %s", exc)
        return {"success": True, "crm": crm, "call_log_id": call_log_id}

    @http.route(
        "/doorway/api/maison-immo-qc/qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.maison_immo_qc_service import (
            MaisonImmoQcService,
        )

        return {
            "success": True,
            "crm": MaisonImmoQcService(request.env(su=True)).process_qualified(payload),
        }

    @http.route(
        "/doorway/api/maison-immo-qc/non-qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def non_qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.maison_immo_qc_service import (
            MaisonImmoQcService,
        )

        return {
            "success": True,
            "crm": MaisonImmoQcService(request.env(su=True)).process_non_qualified(payload),
        }

    @http.route(
        "/doorway/api/maison-immo-qc/dial",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def dial(self, tenant_api_key, telephone, **payload):
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
            campaign = payload.get("campaign") or "MR_IMMO_QC"
            result = svc.call_out_number(digits, campaign=campaign, phone_code="1")
            return {"success": True, "ok": True, "telephone": telephone, "campaign": campaign, "raw": result}
        except Exception as exc:
            _logger.exception("Maison MR QC dial failed: %s", exc)
            return {"success": False, "ok": False, "error": str(exc)}
