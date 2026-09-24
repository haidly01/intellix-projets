# -*- coding: utf-8 -*-
import logging
import re
import subprocess

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SofiaEsApiController(http.Controller):
    def _tenant_from_key(self, tenant_api_key):
        return request.env["doorway.tenant"].get_tenant_by_api_key(tenant_api_key)

    @http.route(
        "/doorway/api/sofia-es/dial",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def dial(self, tenant_api_key, telephone, **payload):
        """Lance un appel sortant Sofia ES via Asterisk/TrustSIP."""
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key", "ok": False}
        digits = re.sub(r"\D", "", telephone or "")
        if not digits:
            return {"success": False, "error": "telephone_required", "ok": False}
        dial_script = "/usr/local/bin/doorway-sofia-dial.sh"
        campaign = "DW_ESREN"
        trunk = "TrustSIP-Espagne"
        if tenant.demo_call_center:
            dial_script = "/usr/local/bin/doorway-sofia-demo-dial.sh"
            campaign = payload.get("campaign") or "ABD_DEMO"
            trunk = "TrustSIP"
        try:
            proc = subprocess.run(
                ["sudo", dial_script, digits],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            ok = proc.returncode == 0
            return {
                "success": ok,
                "ok": ok,
                "telephone": telephone,
                "provider": "vicidial",
                "trunk": trunk,
                "campaign": campaign,
                "demo": bool(tenant.demo_call_center),
                "raw": (proc.stdout or proc.stderr or "")[:500],
            }
        except (subprocess.SubprocessError, OSError) as exc:
            _logger.exception("Sofia ES dial failed: %s", exc)
            return {"success": False, "ok": False, "error": str(exc)}

    @http.route(
        "/doorway/api/sofia-es/call-ended",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, tenant_api_key, **payload):
        """
        Fin d'appel Sofia ES — facturation + mise à jour CRM.
        Payload: call_sid, duration_seconds, amd_result, partner_id, lead_gagnant,
        propietario, tipo_vivienda, codigo_postal, nombre, telephone, email,
        etat_final, transcript, recording_url, campaign
        """
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}

        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        billing = CreditEngine(request.env(su=True)).debit_sofia_es_call(
            tenant.id,
            {
                "call_sid": payload.get("call_sid"),
                "duration_seconds": payload.get("duration_seconds"),
                "amd_result": payload.get("amd_result"),
                "campaign": payload.get("campaign") or "sofia_es_avatrade",
            },
        )

        crm_result = {}
        call_log_id = False
        company_id = tenant.company_id.id if tenant else False
        try:
            from odoo.addons.doorway_agents_dashboard.services.sofia_es_service import (
                SofiaEsService,
            )

            crm_result = SofiaEsService(request.env).process_call_ended(
                payload, company_id=company_id
            )
        except Exception as exc:
            _logger.exception("Sofia ES CRM update failed: %s", exc)
            crm_result = {"ok": False, "error": str(exc)}

        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            log_rec = VicidialService(request.env(su=True)).upsert_call_from_pipeline(
                {
                    **payload,
                    "campaign": payload.get("campaign")
                    or ("ABD_DEMO" if tenant.demo_call_center else "DW_ESREN"),
                },
                company_id=company_id,
            )
            if log_rec:
                call_log_id = log_rec.id
        except Exception as exc:
            _logger.exception("Sofia ES call log upsert failed: %s", exc)

        return {
            "success": True,
            "billing": billing,
            "crm": crm_result,
            "call_log_id": call_log_id,
        }

    @http.route(
        "/doorway/api/sofia-es/call-recording",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_recording(self, tenant_api_key, call_sid, recording_url, **payload):
        """Enregistrement Sofia prêt — upsert doorway.call.log (temps réel)."""
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
                    "campaign": payload.get("campaign")
                    or ("ABD_DEMO" if tenant.demo_call_center else "DW_ESREN"),
                },
                company_id=company_id,
                fast=True,
            )
            return {
                "success": True,
                "call_log_id": log_rec.id if log_rec else False,
            }
        except Exception as exc:
            _logger.exception("Sofia ES call recording upsert failed: %s", exc)
            return {"success": False, "error": str(exc)}
