# -*- coding: utf-8 -*-
"""Stripe Checkout pour réservations villas Coins Marocain (CAD uniquement)."""
from __future__ import annotations

import logging
import os

from odoo import _
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)


def _conf_get(*names: str) -> str:
    """ICP / env / odoo-server.conf (clés lower-casées par Odoo)."""
    for name in names:
        val = os.environ.get(name) or ""
        if val:
            return val
        # odoo-server.conf: STRIPE_API_KEY → config option stripe_api_key
        opt = odoo_config.get(name) or odoo_config.get(name.lower())
        if opt:
            return str(opt)
    return ""


class CoinsStripeService:
    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _config(self):
        base = self._icp.get_param("web.base.url", "https://intellixcrm.com")
        return {
            "secret": (
                self._icp.get_param("coins_marocain.stripe_secret_key")
                or _conf_get("STRIPE_API_KEY", "STRIPE_SECRET_KEY")
            ),
            "publishable": (
                self._icp.get_param("coins_marocain.stripe_publishable_key")
                or _conf_get("STRIPE_PUBLISHABLE_KEY")
            ),
            "webhook_secret": (
                self._icp.get_param("coins_marocain.stripe_webhook_secret")
                or _conf_get("STRIPE_WEBHOOK_SECRET")
            ),
            "success_url": self._icp.get_param(
                "coins_marocain.stripe_success_url",
                "https://coinsmarocain.com/forfaits?booking=success",
            ),
            "cancel_url": self._icp.get_param(
                "coins_marocain.stripe_cancel_url",
                "https://coinsmarocain.com/forfaits?booking=cancel",
            ),
            "base_url": base,
        }

    def is_configured(self):
        return bool(self._config()["secret"])

    def _stripe(self):
        import stripe

        cfg = self._config()
        stripe.api_key = cfg["secret"]
        return stripe

    def create_checkout_session(self, reservation):
        """Crée une session Stripe Checkout en CAD. Retourne l'objet session."""
        if not self.is_configured():
            raise RuntimeError(_("Stripe non configuré (clé secrète absente)."))
        stripe = self._stripe()
        cfg = self._config()
        amount_cents = int(round((reservation.amount_total or 0.0) * 100))
        if amount_cents < 50:
            raise ValueError(_("Montant trop faible pour Stripe (min 0,50 CAD)."))

        line_items = [
            {
                "price_data": {
                    "currency": "cad",
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": _("Séjour %s") % (reservation.property_id.name or ""),
                        "description": _("%(cin)s → %(cout)s · %(n)s nuit(s)")
                        % {
                            "cin": reservation.check_in,
                            "cout": reservation.check_out,
                            "n": reservation.nights or 0,
                        },
                    },
                },
                "quantity": 1,
            }
        ]
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=line_items,
            success_url=cfg["success_url"] + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cfg["cancel_url"],
            customer_email=reservation.client_email or None,
            metadata={
                "reservation_id": str(reservation.id),
                "coins_module": "coins_marocain",
            },
            client_reference_id=str(reservation.id),
        )
        return session

    def construct_webhook_event(self, payload: bytes, sig_header: str):
        stripe = self._stripe()
        secret = self._config()["webhook_secret"]
        if not secret:
            raise RuntimeError(_("Webhook secret Stripe manquant."))
        return stripe.Webhook.construct_event(payload, sig_header, secret)

    def refund_session_payment(self, payment_intent_id: str, reason: str = ""):
        if not payment_intent_id:
            return False
        stripe = self._stripe()
        try:
            stripe.Refund.create(
                payment_intent=payment_intent_id,
                reason="requested_by_customer",
                metadata={"coins_reason": (reason or "")[:200]},
            )
            return True
        except Exception:
            _logger.exception("Stripe refund failed pi=%s", payment_intent_id)
            return False
