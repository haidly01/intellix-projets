# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class PeopleEngineCoachingApi(http.Controller):
    @http.route(
        "/people_engine/coaching/session/<int:session_id>/status",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def session_status(self, session_id, **kwargs):
        session = request.env["pe.coaching.session"].browse(session_id)
        if not session.exists():
            return request.make_response(
                json.dumps({"error": "not_found"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )
        session.check_access("read")
        payload = {
            "id": session.id,
            "status": session.status,
            "manager_approved": session.manager_approved,
            "hr_validated": session.hr_validated,
            "hr_validation_required": session.hr_validation_required,
            "compliance_ok": session.compliance_ok,
            "can_deliver": session.status == "approved"
            and session.final_message
            and (
                not session.hr_validation_required or session.hr_validated
            ),
        }
        return request.make_response(
            json.dumps(payload),
            headers=[("Content-Type", "application/json")],
        )
