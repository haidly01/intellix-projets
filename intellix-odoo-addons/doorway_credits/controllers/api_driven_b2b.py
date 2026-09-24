# -*- coding: utf-8 -*-
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DrivenB2bApiController(http.Controller):
    def _tenant_from_key(self, tenant_api_key):
        return request.env["doorway.tenant"].get_tenant_by_api_key(tenant_api_key)

    @http.route(
        "/doorway/api/driven-b2b/call-ended",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.driven_b2b_service import (
            DrivenB2bService,
        )

        crm = DrivenB2bService(request.env(su=True)).process_post_call(payload)
        return {"success": True, "crm": crm}

    @http.route(
        "/doorway/api/driven-b2b/qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.driven_b2b_service import (
            DrivenB2bService,
        )

        return DrivenB2bService(request.env(su=True)).process_qualified(payload)

    @http.route(
        "/doorway/api/driven-b2b/non-qualified",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def non_qualified(self, tenant_api_key, **payload):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.driven_b2b_service import (
            DrivenB2bService,
        )

        return DrivenB2bService(request.env(su=True)).process_non_qualified(payload)

    @http.route(
        "/doorway/api/driven-b2b/dial",
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
            campaign = payload.get("campaign") or "DW_QCB2B"
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
            _logger.exception("Driven B2B dial failed: %s", exc)
            return {"success": False, "ok": False, "error": str(exc)}

    @http.route(
        "/doorway/api/driven-b2b/daily-stats",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def daily_stats(self, tenant_api_key, date=None, **kwargs):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_agents_dashboard.services.driven_b2b_service import (
            DrivenB2bService,
        )

        stats = DrivenB2bService(request.env(su=True)).daily_stats(date)
        return {"success": True, **stats}
