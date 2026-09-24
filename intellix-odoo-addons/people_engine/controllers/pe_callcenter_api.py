# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

OUTCOME_MAP = {
    "qualifie": "interesse",
    "rdv": "demo_bookee",
    "a_rappeler": "rappel",
    "pas_interesse": "pas_interesse",
    "messagerie": "rappel",
    "dnc": "pas_interesse",
    "faux_num": "mauvais_num",
    "qualifie_chaud": "interesse",
    "vendu": "vendu",
    "demo_bookee": "demo_bookee",
    "interesse": "interesse",
}


class PeCallcenterApi(http.Controller):

    @http.route(
        "/pe/callcenter/wall/data",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def wall_data(self, **kwargs):
        data = (
            request.env["pe.callcenter.service"]
            .sudo()
            .get_wall_dashboard_data()
        )
        return request.make_response(
            json.dumps(data),
            headers=[("Content-Type", "application/json")],
        )

    @http.route(
        "/api/pe/call_log/create",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def api_create_call_log(self, **kwargs):
        """Webhook n8n post-appel : crée un pe.call.log avec score IA."""
        payload = request.jsonrequest or {}
        api_key = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("people_engine.call_log_api_key")
        )
        if api_key:
            provided = request.httprequest.headers.get("X-PE-API-Key") or payload.get(
                "api_key"
            )
            if provided != api_key:
                return {"ok": False, "error": "unauthorized"}

        employee_id = payload.get("employee_id")
        vicidial_user = payload.get("vicidial_user")
        if not employee_id and vicidial_user:
            profile = (
                request.env["pe.employee.profile"]
                .sudo()
                .search([("vicidial_user", "=", vicidial_user)], limit=1)
            )
            if profile:
                employee_id = profile.employee_id.id

        if not employee_id:
            return {"ok": False, "error": "employee_not_found"}

        outcome_raw = payload.get("outcome") or payload.get("qualification") or "interesse"
        outcome = OUTCOME_MAP.get(outcome_raw, "interesse")

        vals = {
            "employee_id": employee_id,
            "lead_id": payload.get("lead_id"),
            "campaign_id": payload.get("campaign_id"),
            "duration": int(payload.get("duration") or 0),
            "vicidial_id": payload.get("vicidial_id") or payload.get("vicidial_call_id"),
            "outcome": outcome,
            "recording_url": payload.get("recording_url"),
            "transcript": payload.get("transcript"),
            "ai_score": float(payload.get("ai_score") or 0),
            "ai_feedback": payload.get("ai_feedback"),
            "ai_strengths": payload.get("ai_strengths"),
            "ai_improvements": payload.get("ai_improvements"),
        }
        if payload.get("date_call"):
            vals["date_call"] = payload["date_call"]

        try:
            log = request.env["pe.call.log"].sudo().create(vals)
            return {"ok": True, "id": log.id, "points": log.points_awarded}
        except Exception as exc:
            _logger.exception("PE call log webhook: %s", exc)
            return {"ok": False, "error": str(exc)}

    @http.route(
        "/pe/workstation/pause/<string:pause_type>",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def workstation_typed_pause(self, pause_type, **kwargs):
        """Pause typée depuis le poste VICIdial (pausette, dejeuner, personnelle)."""
        Session = request.env["doorway.vicidial.agent.session"].sudo()
        session = Session.get_active_session()
        if not session:
            return request.make_response(
                json.dumps({"error": "no_session"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )
        mapping = {
            "pausette": "action_pause_pausette",
            "dejeuner": "action_pause_dejeuner",
            "personnelle": "action_pause_personnelle",
        }
        method = mapping.get(pause_type)
        if not method or not hasattr(session, method):
            return request.make_response(
                json.dumps({"error": "invalid_pause_type"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )
        try:
            data = getattr(session, method)()
            return request.make_response(
                json.dumps({"ok": True, "session": data}),
                headers=[("Content-Type", "application/json")],
            )
        except Exception as exc:  # noqa: BLE001
            return request.make_response(
                json.dumps({"error": str(exc)}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

    @http.route(
        "/pe/supervisor/pause/status",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def supervisor_pause_status(self, **kwargs):
        data = (
            request.env["pe.payroll.service"]
            .sudo()
            .get_supervisor_pause_status()
        )
        return request.make_response(
            json.dumps(data),
            headers=[("Content-Type", "application/json")],
        )
