# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CreditApiController(http.Controller):
    def _tenant_from_key(self, tenant_api_key):
        return request.env["doorway.tenant"].get_tenant_by_api_key(tenant_api_key)

    @http.route(
        "/doorway/api/credits/check",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def check_credits(self, tenant_api_key, service, quantity=1):
        """Vérifie le solde sans débiter."""
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"can_proceed": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        result = CreditEngine(request.env).check_balance(tenant.id, service, quantity)
        return {
            "can_proceed": result["can_proceed"],
            "balance": result["balance"],
            "required": result.get("required", 0),
        }

    @http.route(
        "/doorway/api/credits/debit",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def debit_credits(
        self, tenant_api_key, service, quantity=1, description=None, reference_id=None
    ):
        """Débite des crédits après consommation."""
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"success": False, "error": "invalid_api_key"}
        from odoo.addons.doorway_credits.services.credit_engine import CreditEngine

        return CreditEngine(request.env).debit_service(
            tenant.id,
            service,
            quantity=quantity,
            call_id=reference_id,
            description=description,
        )

    @http.route(
        "/doorway/api/credits/balance",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def get_balance(self, tenant_api_key):
        tenant = self._tenant_from_key(tenant_api_key)
        if not tenant:
            return {"error": "invalid_api_key"}
        return {"balance": tenant.credit_balance, "status": tenant.status}

    @http.route(
        "/doorway/api/credits/checkout",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def create_checkout(self, pack_id, tenant_id=None):
        """Crée une session Stripe Checkout (utilisateur Odoo connecté)."""
        tenant = request.env["doorway.tenant"].browse(int(tenant_id)) if tenant_id else (
            request.env["doorway.tenant"].get_tenant_for_company()
        )
        if not tenant:
            return {"error": "no_tenant"}
        pack = request.env["doorway.credit.pack"].browse(int(pack_id))
        from odoo.addons.doorway_credits.services.stripe_service import StripeService

        url = StripeService(request.env).create_checkout_session(tenant, pack)
        return {"checkout_url": url}
