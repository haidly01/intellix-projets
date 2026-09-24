# -*- coding: utf-8 -*-
import json
from datetime import date, datetime

from odoo import http
from odoo.http import request


class VicidialWorkstationController(http.Controller):

    def _check_access(self):
        return request.env.user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_qualifier"
        )

    def _json_default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat(sep=" ", timespec="seconds")
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, default=self._json_default),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

    def _json_body(self, kwargs):
        """Fusionne les paramètres de formulaire et le corps JSON éventuel."""
        data = dict(kwargs or {})
        raw = request.httprequest.get_data(as_text=True) or ""
        if raw.strip():
            try:
                body = json.loads(raw)
                if isinstance(body, dict):
                    data.update(body)
            except (TypeError, ValueError):
                pass
        return data

    def _session_model(self):
        return request.env["doorway.vicidial.agent.session"].sudo()

    @http.route(
        "/doorway/vicidial/workstation",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def workstation_data(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        light = str(kwargs.get("light") or "").lower() in ("1", "true", "yes")
        data = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_workstation_data(light=light)
        )
        return self._json_response(data)

    @http.route(
        "/doorway/vicidial/workstation/start",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def start_session(self, campaign_id=None, callback_phone=None, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        if not campaign_id:
            return self._json_response({"error": "campaign_required"}, status=400)
        try:
            session = (
                request.env["doorway.vicidial.agent.session"]
                .sudo()
                .action_start_session(
                    int(campaign_id),
                    callback_phone=(callback_phone or "").strip() or None,
                )
            )
            return self._json_response({"session": session})
        except Exception as exc:  # noqa: BLE001
            return self._json_response({"error": str(exc)}, status=400)

    @http.route(
        "/doorway/vicidial/workstation/pause",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def pause_session(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session:
            return self._json_response({"error": "no_session"}, status=400)
        return self._json_response(
            {"session": session.action_pause_session()}
        )

    @http.route(
        "/doorway/vicidial/workstation/resume",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def resume_session(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session:
            return self._json_response({"error": "no_session"}, status=400)
        return self._json_response(
            {"session": session.action_resume_session()}
        )

    @http.route(
        "/doorway/vicidial/workstation/end",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def end_session(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session:
            return self._json_response({"error": "no_session"}, status=400)
        return self._json_response({"session": session.action_end_session()})

    @http.route(
        "/doorway/vicidial/workstation/dial-next",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def dial_next(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session or session.state != "active":
            return self._json_response({"error": "no_session"}, status=400)
        data = self._json_body(kwargs)
        group_alias_id = data.get("group_alias_id")
        if group_alias_id is None:
            group_alias_id = session.outbound_group_alias_id
        try:
            result = session.action_dial_next(group_alias_id=group_alias_id)
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            svc = VicidialService(request.env)
            return self._json_response(
                {
                    "ok": True,
                    "lead_id": result.get("lead_id") or "",
                    "phone_number": result.get("phone_number") or "",
                    "vicidial_live": svc.get_agent_live_status(session.vicidial_user),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return self._json_response({"error": str(exc)}, status=400)

    @http.route(
        "/doorway/vicidial/workstation/manual_dial",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def manual_dial(self, phone=None, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session or session.state != "active":
            return self._json_response({"error": "no_session"}, status=400)
        data = self._json_body(kwargs)
        raw_phone = (phone or data.get("phone_number") or data.get("phone") or "").strip()
        if not raw_phone:
            raw = request.httprequest.get_data(as_text=True) or ""
            if raw.strip():
                try:
                    body = json.loads(raw)
                    raw_phone = (
                        body.get("phone") or body.get("phone_number") or ""
                    ).strip()
                except (TypeError, ValueError):
                    raw_phone = raw.strip()
        if not raw_phone:
            return self._json_response({"error": "phone_required"}, status=400)
        group_alias_id = data.get("group_alias_id")
        if group_alias_id is None:
            group_alias_id = session.outbound_group_alias_id
        try:
            result = session.action_manual_dial(raw_phone, group_alias_id=group_alias_id)
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            svc = VicidialService(request.env)
            return self._json_response(
                {
                    "ok": True,
                    "lead_id": result.get("lead_id") or "",
                    "phone_number": result.get("phone_number") or "",
                    "vicidial_live": svc.get_agent_live_status(session.vicidial_user),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return self._json_response({"error": str(exc)}, status=400)

    @http.route(
        "/doorway/vicidial/workstation/hangup",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def hangup_call(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(request.env)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        vicidial_user = None
        session_name = None
        campaign_id = None
        conf_exten = None
        if session and session.state == "active":
            vicidial_user = session.vicidial_user
            session_name = session.vicidial_session_name
            campaign_id = (
                session.campaign_id.vicidial_campaign_id
                if session.campaign_id
                else None
            )
        else:
            agent = (
                request.env["doorway.campaign.agent.user"]
                .sudo()
                .search([("user_id", "=", request.env.user.id)], limit=1)
            )
            if agent:
                vicidial_user = agent.vicidial_user
            live = svc.get_agent_live_status(vicidial_user or "")
            if not live.get("logged_in") and not live.get("conf_exten"):
                return self._json_response({"error": "no_session"}, status=400)
            conf_exten = live.get("conf_exten")
            session_name = svc.resolve_vicidial_session_name(vicidial_user)
            campaign_id = live.get("campaign_id")
        if not vicidial_user:
            return self._json_response({"error": "no_session"}, status=400)
        try:
            if session and session.state == "active":
                result = session.action_hangup_call()
            else:
                result = svc.hangup_agent_call(
                    vicidial_user,
                    session_name=session_name,
                    campaign_id=campaign_id,
                    conf_exten=conf_exten,
                )
            return self._json_response(
                {
                    "ok": True,
                    "skipped": bool(result.get("skipped")),
                    "message": result.get("message") or "",
                    "hung_channels": result.get("hung_channels") or [],
                    "vicidial_live": svc.get_agent_live_status(vicidial_user),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return self._json_response({"error": str(exc)}, status=400)

    @http.route(
        "/doorway/vicidial/workstation/set_outbound_alias",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def set_outbound_alias(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session:
            return self._json_response({"error": "no_session"}, status=400)
        data = self._json_body(kwargs)
        result = session.action_set_outbound_group_alias(
            group_alias_id=data.get("group_alias_id")
        )
        return self._json_response(result)

    @http.route(
        "/doorway/vicidial/workstation/heartbeat",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def heartbeat(self, **kwargs):
        """Heartbeat natif conf_exten_check (équivalent check_for_conf_calls JS)."""
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        session = (
            request.env["doorway.vicidial.agent.session"]
            .sudo()
            .get_active_session()
        )
        if not session or session.state != "active":
            return self._json_response({"error": "no_session"}, status=400)
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(request.env)
        campaign_vicidial_id = (
            session.campaign_id.vicidial_campaign_id if session.campaign_id else ""
        )
        sync = svc.sync_agent_ready_for_session(
            session.vicidial_user,
            campaign_vicidial_id,
            session_name=session.vicidial_session_name,
        )
        synced_name = (sync.get("session_name") or "").strip()
        if synced_name and synced_name != (session.vicidial_session_name or ""):
            session.sudo().write({"vicidial_session_name": synced_name})
        live = svc.get_agent_live_status(session.vicidial_user)
        if not session.vicidial_session_name or not live.get("conf_exten"):
            hb = {"ok": svc.touch_agent_heartbeat(session.vicidial_user)}
        else:
            hb = svc.send_conf_exten_heartbeat(
                session.vicidial_user,
                session.vicidial_session_name,
                session.campaign_id.vicidial_campaign_id,
                live.get("conf_exten"),
            )
            if not hb.get("ok"):
                svc.touch_agent_heartbeat(session.vicidial_user)
        phone_ext = svc.get_agent_phone_extension(session.vicidial_user)
        if phone_ext and live.get("conf_exten") and svc.get_pjsip_registered(phone_ext):
            if not svc._agent_in_confbridge(phone_ext, live.get("conf_exten")):
                svc.ensure_webphone_in_conference(
                    session.vicidial_user, live.get("conf_exten")
                )
        svc.recover_agent_after_webphone_hangup(
            session.vicidial_user, live.get("conf_exten")
        )
        live = svc.get_agent_live_status(session.vicidial_user)
        webphone_ready = svc.get_webphone_call_ready(
            session.vicidial_user, live.get("conf_exten")
        )
        sync_evt = (
            request.env["doorway.vicidial.call.sync"]
            .sudo()
            .sync_for_current_user()
        )
        return self._json_response(
            {
                "ok": bool(hb.get("ok")),
                "vicidial_live": live,
                "webphone_registered": webphone_ready,
                "webphone_call_ready": webphone_ready,
                "sync_event": sync_evt.get("event") if isinstance(sync_evt, dict) else None,
            }
        )

    # ------------------------------------------------------------------
    # Hub d'appels : appels récents, fiche CRM, notes, activités, messages
    # ------------------------------------------------------------------

    @http.route(
        "/doorway/vicidial/workstation/recent_calls",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def recent_calls(self, kind="all", search=None, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        calls = self._session_model().get_recent_calls(
            kind=kind or "all", search=search
        )
        return self._json_response({"calls": calls})

    @http.route(
        "/doorway/vicidial/workstation/contact",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def contact_fiche(self, phone=None, lead_id=None, partner_id=None, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        fiche = self._session_model().get_contact_fiche(
            phone=phone,
            lead_id=int(lead_id) if lead_id else None,
            partner_id=int(partner_id) if partner_id else None,
        )
        return self._json_response({"contact": fiche})

    @http.route(
        "/doorway/vicidial/workstation/note",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def save_note(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        data = self._json_body(kwargs)
        result = self._session_model().workstation_save_note(
            data.get("note"),
            lead_id=data.get("lead_id"),
            partner_id=data.get("partner_id"),
        )
        status = 200 if result.get("ok") else 400
        return self._json_response(result, status=status)

    @http.route(
        "/doorway/vicidial/workstation/activity",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def create_activity(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        data = self._json_body(kwargs)
        result = self._session_model().workstation_create_activity(
            kind=data.get("kind") or "task",
            lead_id=data.get("lead_id"),
            partner_id=data.get("partner_id"),
            summary=data.get("summary"),
            note=data.get("note"),
            date_deadline=data.get("date_deadline"),
        )
        status = 200 if result.get("ok") else 400
        return self._json_response(result, status=status)

    @http.route(
        "/doorway/vicidial/workstation/qualify",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def apply_qualification(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        data = self._json_body(kwargs)
        result = self._session_model().workstation_apply_qualification(
            data.get("statut"),
            lead_id=data.get("lead_id"),
            partner_id=data.get("partner_id"),
            note=data.get("note"),
        )
        status = 200 if result.get("ok") else 400
        return self._json_response(result, status=status)

    @http.route(
        "/doorway/vicidial/workstation/send_message",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def send_message(self, **kwargs):
        if not self._check_access():
            return self._json_response({"error": "no_access"}, status=403)
        data = self._json_body(kwargs)
        result = self._session_model().workstation_send_message(
            data.get("channel"),
            data.get("phone"),
            body=data.get("body"),
            lead_id=data.get("lead_id"),
            partner_id=data.get("partner_id"),
        )
        status = 200 if result.get("ok") else 400
        return self._json_response(result, status=status)
