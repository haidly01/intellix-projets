# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class StripeWebhookController(http.Controller):
    @http.route(
        "/doorway/stripe/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def stripe_webhook(self, **kwargs):
        """Webhook Stripe — vérifie la signature puis traite l'événement."""
        payload = request.httprequest.data
        sig = request.httprequest.headers.get("Stripe-Signature", "")
        from odoo.addons.doorway_credits.services.stripe_service import StripeService

        svc = StripeService(request.env)
        if not svc.is_configured():
            return http.Response("Stripe not configured", status=503)
        try:
            event = svc.verify_webhook(payload, sig)
        except Exception as error:  # noqa: BLE001
            _logger.warning("Webhook Stripe signature invalide : %s", error)
            return http.Response("Invalid signature", status=400)

        event_type = event.get("type")
        handlers = {
            "checkout.session.completed": svc.handle_payment_succeeded,
            "payment_intent.succeeded": svc.handle_payment_succeeded,
            "customer.subscription.updated": svc.handle_subscription_updated,
            "customer.subscription.deleted": svc.handle_subscription_deleted,
            "invoice.paid": svc.handle_invoice_paid,
            "invoice.payment_failed": svc.handle_payment_failed,
        }
        handler = handlers.get(event_type)
        if handler:
            try:
                handler(event)
            except Exception:  # noqa: BLE001
                _logger.exception("Erreur traitement Stripe %s", event_type)
        return http.Response(json.dumps({"received": True}), status=200)

    @http.route("/doorway/credits/success", type="http", auth="user")
    def credits_success(self, session_id=None, **kw):
        return request.redirect("/web#action=doorway_credits.action_tenant_dashboard")

    @http.route("/doorway/credits/cancel", type="http", auth="user")
    def credits_cancel(self, **kw):
        return request.redirect("/web#action=doorway_credits.action_tenant_dashboard")
