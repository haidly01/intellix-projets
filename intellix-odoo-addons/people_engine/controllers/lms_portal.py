# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PeopleEngineLMSPortal(http.Controller):

    @http.route("/people-engine/my-training", type="http", auth="user", website=True)
    def my_training(self, **kwargs):
        employee = request.env.user.employee_id
        if not employee:
            return request.not_found()
        profile = request.env["pe.employee.profile"].search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if not profile:
            return request.render(
                "people_engine.lms_portal_empty",
                {"message": "Aucun profil People Engine."},
            )
        enrollments = request.env["pe.enrollment"].search(
            [
                ("profile_id", "=", profile.id),
                ("status", "in", ["not_started", "in_progress"]),
            ]
        )
        paths = request.env["pe.learning.path"].search(
            [
                ("profile_id", "=", profile.id),
                ("status", "=", "active"),
            ]
        )
        return request.render(
            "people_engine.lms_portal_my_training",
            {
                "profile": profile,
                "enrollments": enrollments,
                "paths": paths,
            },
        )
