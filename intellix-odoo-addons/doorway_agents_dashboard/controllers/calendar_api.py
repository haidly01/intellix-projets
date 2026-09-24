# -*- coding: utf-8 -*-
"""API calendrier — disponibilité et création de visioconférence."""
import json
import logging

from odoo import fields, http
from odoo.http import request

from odoo.addons.doorway_agents_dashboard.services.calendar_availability_service import (
    CalendarAvailabilityService,
)

_logger = logging.getLogger(__name__)

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


class DoorwayCalendarApiController(http.Controller):
    def _json_body(self):
        raw = request.httprequest.data.decode("utf-8", errors="replace")
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return None

    def _check_webhook_or_user(self, data):
        token = (
            data.get("webhook_key")
            or request.httprequest.headers.get("X-Doorway-Webhook-Key")
        )
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_agents_dashboard.webhook_token")
        )
        if token and expected and token == expected:
            return True
        return request.env.user and not request.env.user._is_public()

    @http.route(
        "/api/intellix/calendar/availability",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def calendar_availability(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        data = self._json_body()
        if data is None:
            return request.make_json_response(
                {"status": "error", "message": "JSON invalide."}, status=400, headers=CORS
            )
        if not self._check_webhook_or_user(data):
            return request.make_json_response(
                {"status": "error", "message": "Non autorisé."}, status=401, headers=CORS
            )
        env = request.env(su=True) if data.get("webhook_key") else request.env
        svc = CalendarAvailabilityService(env)
        refs = data.get("partner_ids") or data.get("participants") or []
        if data.get("agent_id"):
            refs = list(refs) + [data["agent_id"]]
        if data.get("user_id"):
            user = env["res.users"].browse(int(data["user_id"]))
            if user.exists():
                refs = list(refs) + [user.partner_id.id]
        if not refs:
            return request.make_json_response(
                {"status": "error", "message": "partner_ids ou agent_id requis."},
                status=400,
                headers=CORS,
            )
        if data.get("day") and not data.get("start"):
            result = svc.find_free_slots(
                refs,
                data["day"],
                duration_minutes=int(data.get("duration_minutes", 30)),
                tz_name=data.get("timezone", "America/Toronto"),
                work_start=int(data.get("work_start", 9)),
                work_end=int(data.get("work_end", 17)),
            )
            return request.make_json_response({"status": "ok", **result}, headers=CORS)
        start = data.get("start")
        stop = data.get("stop")
        if not start or not stop:
            return request.make_json_response(
                {"status": "error", "message": "start/stop ou day requis."},
                status=400,
                headers=CORS,
            )
        result = svc.check_availability(
            refs, start, stop, tz_name=data.get("timezone")
        )
        return request.make_json_response({"status": "ok", **result}, headers=CORS)

    @http.route(
        "/api/intellix/calendar/meeting",
        type="http",
        auth="user",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def calendar_create_meeting(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)
        data = self._json_body()
        if data is None:
            return request.make_json_response(
                {"status": "error", "message": "JSON invalide."}, status=400, headers=CORS
            )
        name = data.get("name") or "Rendez-vous"
        start = data.get("start")
        stop = data.get("stop")
        if not start or not stop:
            return request.make_json_response(
                {"status": "error", "message": "start et stop requis."},
                status=400,
                headers=CORS,
            )
        partner_ids = list(data.get("partner_ids") or [])
        partner_ids.append(request.env.user.partner_id.id)
        agent_id = data.get("agent_profile_id")
        if agent_id:
            profile = request.env["doorway.agent.profile"].browse(int(agent_id))
            if profile.calendar_partner_id:
                partner_ids.append(profile.calendar_partner_id.id)
        partner_ids = list(set(int(p) for p in partner_ids))
        event = request.env["calendar.event"].doorway_create_meeting_with_videocall(
            name=name,
            start=start,
            stop=stop,
            partner_ids=partner_ids,
            user_id=request.env.user.id,
            agent_profile_id=int(agent_id) if agent_id else None,
            description=data.get("description"),
        )
        join_url = event.videocall_location
        if join_url and "/calendar/join_videocall/" in join_url:
            base = request.httprequest.host_url.rstrip("/")
            join_url = f"{base}{join_url}" if join_url.startswith("/") else join_url
        return request.make_json_response(
            {
                "status": "ok",
                "event_id": event.id,
                "name": event.name,
                "start": fields.Datetime.to_string(event.start),
                "stop": fields.Datetime.to_string(event.stop),
                "videocall_location": join_url,
            },
            headers=CORS,
        )
