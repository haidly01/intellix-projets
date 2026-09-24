# -*- coding: utf-8 -*-
import json
import os

from odoo import http
from odoo.modules.module import get_module_path
from odoo.http import request


class AgentsDashboardHealthController(http.Controller):
    @http.route(
        "/api/agents/dashboard/health",
        auth="public",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def dashboard_health(self, **kwargs):
        module_path = get_module_path("doorway_agents_dashboard") or ""
        template_path = os.path.join(
            module_path, "static", "src", "xml", "agents_dashboard.xml"
        )
        js_path = os.path.join(
            module_path, "static", "src", "js", "agents_dashboard.js"
        )
        css_path = os.path.join(
            module_path, "static", "src", "css", "agents.css"
        )
        payload = {
            "ok": True,
            "module": "doorway_agents_dashboard",
            "template_name": "doorway_agents_dashboard.AgentsDashboard",
            "files": {
                "template_xml_exists": os.path.exists(template_path),
                "js_exists": os.path.exists(js_path),
                "css_exists": os.path.exists(css_path),
            },
            "hint": "Si erreur OWL persistante, faire Ctrl+Shift+R et vider le cache navigateur.",
        }
        return request.make_response(
            json.dumps(payload),
            headers=[("Content-Type", "application/json")],
        )
