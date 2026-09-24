# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-LinkedIn-Scraper-Key, X-Zakaria-Key",
}


class LinkedInScraperController(http.Controller):
    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status, headers=CORS)

    def _parse_body(self, kwargs):
        req = request.httprequest
        if req.data:
            raw = req.data.decode("utf-8", errors="replace").strip()
            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass
        return dict(kwargs) if kwargs else {}

    def _expected_api_key(self):
        icp = request.env["ir.config_parameter"].sudo()
        key = (icp.get_param("linkedin.scraper.api_key") or "").strip()
        if key:
            return key
        import os

        return (os.environ.get("LINKEDIN_SCRAPER_API_KEY") or "").strip()

    def _check_api_key(self):
        expected = self._expected_api_key()
        if not expected:
            _logger.warning("linkedin.scraper.api_key non configurée — accès refusé")
            return False
        provided = (
            request.httprequest.headers.get("X-LinkedIn-Scraper-Key")
            or request.httprequest.headers.get("X-Zakaria-Key")
            or ""
        ).strip()
        return provided == expected

    @http.route(
        "/api/linkedin/receive_cookies",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def receive_cookies(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)

        if not self._check_api_key():
            return self._json({"success": False, "error": "Unauthorized"}, 401)

        data = self._parse_body(kwargs)
        cookies = (data.get("cookies") or "").strip()
        user_agent = (data.get("user_agent") or "").strip()
        user_label = (data.get("user") or "karine").strip().lower()

        if not cookies or "li_at=" not in cookies:
            return self._json(
                {
                    "success": False,
                    "error": "Cookie li_at manquant — reconnectez-vous à LinkedIn",
                },
                400,
            )

        icp = request.env["ir.config_parameter"].sudo()
        icp.set_param("linkedin.karine.cookies", cookies)
        icp.set_param("linkedin.karine.user_agent", user_agent)
        icp.set_param("linkedin.karine.last_update", data.get("timestamp") or "")
        icp.set_param("linkedin.karine.user_label", user_label)
        icp.set_param("linkedin.scraper.status", "queued")

        Scraper = request.env["linkedin.scraper"].sudo()
        launched = Scraper.launch_scrape_subprocess(trigger="cookies")

        return self._json(
            {
                "success": True,
                "message": "Cookies enregistrés. Scraping lancé en arrière-plan."
                if launched
                else "Cookies enregistrés. Scraping déjà en cours.",
                "scraping_launched": launched,
            }
        )

    @http.route(
        "/api/linkedin/scraping_status",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
    )
    def scraping_status(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)

        icp = request.env["ir.config_parameter"].sudo()
        return self._json(
            {
                "status": icp.get_param("linkedin.scraper.status", "idle"),
                "leads_found": icp.get_param("linkedin.scraper.leads_found", "0"),
                "last_update": icp.get_param("linkedin.karine.last_update", ""),
                "cookies_present": bool(icp.get_param("linkedin.karine.cookies")),
                "last_run": icp.get_param("linkedin.scraper.last_run", ""),
                "last_csv": icp.get_param("linkedin.scraper.last_csv", ""),
            }
        )

    @http.route(
        "/api/linkedin/import_leads",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def import_leads(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=CORS)

        if not self._check_api_key():
            return self._json({"ok": False, "error": "Unauthorized"}, 401)

        data = self._parse_body(kwargs)
        leads = data.get("leads") or []
        phase2 = bool(data.get("phase2"))

        result = (
            request.env["linkedin.scraper"]
            .sudo()
            .import_linkedin_leads(leads, allow_phase2=phase2)
        )
        return self._json({"ok": True, **result})
