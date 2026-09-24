# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class IntellixLegalController(http.Controller):
    """Pages légales publiques pour l'application Meta / Facebook « Intellix »."""

    def _legal_context(self):
        company = request.env.company
        return {
            "company_name": company.name or "Agence Doorway Inc.",
            "company_email": company.email or "info@agencedoorway.com",
            "company_phone": company.phone or "",
            "company_website": company.website or "https://intellixcrm.com",
            "app_name": "Intellix",
            "last_updated": "1 juin 2026",
        }

    @http.route(
        "/intellix/privacy-policy",
        type="http",
        auth="public",
        website=False,
        sitemap=True,
    )
    def privacy_policy(self, **kwargs):
        return request.render(
            "renovation_conciergerie.intellix_privacy_policy",
            self._legal_context(),
        )

    @http.route(
        "/intellix/terms-of-service",
        type="http",
        auth="public",
        website=False,
        sitemap=True,
    )
    def terms_of_service(self, **kwargs):
        return request.render(
            "renovation_conciergerie.intellix_terms_of_service",
            self._legal_context(),
        )

    @http.route(
        "/intellix/data-deletion",
        type="http",
        auth="public",
        website=False,
        sitemap=True,
    )
    def data_deletion(self, **kwargs):
        return request.render(
            "renovation_conciergerie.intellix_data_deletion",
            self._legal_context(),
        )
