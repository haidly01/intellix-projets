# -*- coding: utf-8 -*-
"""Service Stripe — abonnements et packs de crédits."""
import logging
import os

from odoo import _

_logger = logging.getLogger(__name__)


class StripeService:
    """Paiements Stripe pour la plateforme Doorway SaaS."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _config(self):
        return {
            "secret": self._icp.get_param("doorway_credits.stripe_secret_key")
            or os.environ.get("STRIPE_SECRET_KEY", ""),
            "publishable": self._icp.get_param("doorway_credits.stripe_publishable_key")
            or os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
            "webhook_secret": self._icp.get_param("doorway_credits.stripe_webhook_secret")
            or os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            "sub_price_id": self._icp.get_param("doorway_credits.stripe_subscription_price_id")
            or os.environ.get("STRIPE_SUBSCRIPTION_PRICE_ID", ""),
            "success_url": self._icp.get_param("doorway_credits.stripe_success_url")
            or os.environ.get(
                "STRIPE_SUCCESS_URL",
                "%s/doorway/credits/success" % self._icp.get_param("web.base.url", ""),
            ),
            "cancel_url": self._icp.get_param("doorway_credits.stripe_cancel_url")
            or os.environ.get(
                "STRIPE_CANCEL_URL",
                "%s/doorway/credits/cancel" % self._icp.get_param("web.base.url", ""),
            ),
        }

    def _stripe(self):
        import stripe

        cfg = self._config()
        stripe.api_key = cfg["secret"]
        return stripe

    def is_configured(self):
        return bool(self._config()["secret"])

    def create_customer(self, tenant):
        """Crée un customer Stripe pour un tenant."""
        if not self.is_configured():
            return False
        stripe = self._stripe()
        customer = stripe.Customer.create(
            name=tenant.name,
            email=tenant.email_admin,
            metadata={"tenant_id": str(tenant.id), "odoo_company_id": str(tenant.company_id.id)},
        )
        tenant.sudo().write({"stripe_customer_id": customer.id})
        return customer.id

    def get_or_create_customer(self, tenant):
        if tenant.stripe_customer_id:
            return tenant.stripe_customer_id
        return self.create_customer(tenant)

    def create_subscription(self, tenant, user_count):
        """Abonnement récurrent 89 USD × utilisateurs."""
        if not self.is_configured():
            return False
        cfg = self._config()
        if not cfg["sub_price_id"]:
            _logger.warning("STRIPE_SUBSCRIPTION_PRICE_ID manquant")
            return False
        stripe = self._stripe()
        customer_id = self.get_or_create_customer(tenant)
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": cfg["sub_price_id"], "quantity": max(user_count, 1)}],
            metadata={"tenant_id": str(tenant.id)},
        )
        subscription = tenant.subscription_id or self.env["doorway.subscription"].sudo().create(
            {"tenant_id": tenant.id, "user_count": user_count}
        )
        subscription.write(
            {
                "stripe_subscription_id": sub.id,
                "user_count": user_count,
                "status": sub.status if hasattr(sub, "status") else "active",
            }
        )
        tenant.write({"subscription_id": subscription.id, "status": "active"})
        return sub.id

    def update_subscription_quantity(self, tenant, new_user_count):
        if not tenant.subscription_id or not tenant.subscription_id.stripe_subscription_id:
            return self.create_subscription(tenant, new_user_count)
        stripe = self._stripe()
        sub = stripe.Subscription.retrieve(tenant.subscription_id.stripe_subscription_id)
        item_id = sub["items"]["data"][0]["id"]
        stripe.Subscription.modify(
            sub.id,
            items=[{"id": item_id, "quantity": max(new_user_count, 1)}],
        )
        tenant.subscription_id.write({"user_count": new_user_count})
        return True

    def cancel_subscription(self, tenant, at_period_end=True):
        if not tenant.subscription_id or not tenant.subscription_id.stripe_subscription_id:
            return False
        stripe = self._stripe()
        stripe.Subscription.modify(
            tenant.subscription_id.stripe_subscription_id,
            cancel_at_period_end=at_period_end,
        )
        if not at_period_end:
            tenant.write({"status": "cancelled"})
            tenant.subscription_id.write({"status": "cancelled"})
        return True

    def create_checkout_session(self, tenant, pack, purchase=None):
        """Session Stripe Checkout pour achat de pack.

        ``purchase`` (doorway.credit.purchase) facultatif : sa référence est
        transmise dans les métadonnées Stripe pour un octroi idempotent des
        crédits via le webhook (une seule fois par achat).
        """
        if not self.is_configured():
            raise ValueError("Stripe non configuré")
        stripe = self._stripe()
        cfg = self._config()
        customer_id = self.get_or_create_customer(tenant)
        line_items = []
        if pack.stripe_price_id:
            line_items.append({"price": pack.stripe_price_id, "quantity": 1})
        else:
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": pack.name},
                        "unit_amount": int(pack.price_usd * 100),
                    },
                    "quantity": 1,
                }
            )
        metadata = {
            "tenant_id": str(tenant.id),
            "pack_id": str(pack.id),
            "credits_amount": str(pack.credits_amount),
        }
        if purchase:
            metadata["purchase_id"] = str(purchase.id)
            metadata["purchase_ref"] = purchase.name or ""
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=line_items,
            success_url=cfg["success_url"] + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cfg["cancel_url"],
            metadata=metadata,
        )
        return session.url

    def create_payment_intent(self, tenant, pack):
        """PaymentIntent pour intégration Stripe.js."""
        stripe = self._stripe()
        customer_id = self.get_or_create_customer(tenant)
        intent = stripe.PaymentIntent.create(
            amount=int(pack.price_usd * 100),
            currency="usd",
            customer=customer_id,
            metadata={"tenant_id": str(tenant.id), "pack_id": str(pack.id)},
        )
        return intent.client_secret

    def charge_auto_recharge(self, tenant):
        """Recharge automatique quand solde sous le seuil."""
        if not self.is_configured() or not tenant.stripe_customer_id:
            return False
        amount = tenant.auto_recharge_amount
        stripe = self._stripe()
        pack = self.env["doorway.credit.pack"].search(
            [("credits_amount", ">=", amount), ("is_active", "=", True)],
            order="credits_amount",
            limit=1,
        )
        if not pack:
            return False
        try:
            stripe.PaymentIntent.create(
                amount=int(pack.price_usd * 100),
                currency="usd",
                customer=tenant.stripe_customer_id,
                confirm=True,
                off_session=True,
                payment_method=self._default_payment_method(tenant),
                metadata={
                    "tenant_id": str(tenant.id),
                    "pack_id": str(pack.id),
                    "auto_recharge": "1",
                },
            )
        except Exception as error:  # noqa: BLE001
            _logger.warning("Auto-recharge échouée tenant %s : %s", tenant.id, error)
            return False
        return True

    def _default_payment_method(self, tenant):
        stripe = self._stripe()
        customer = stripe.Customer.retrieve(tenant.stripe_customer_id)
        return customer.get("invoice_settings", {}).get("default_payment_method")

    def verify_webhook(self, payload, sig_header):
        """Vérifie la signature Stripe."""
        cfg = self._config()
        stripe = self._stripe()
        return stripe.Webhook.construct_event(payload, sig_header, cfg["webhook_secret"])

    def handle_payment_succeeded(self, event):
        """checkout.session.completed ou payment_intent.succeeded → créditer."""
        data = event["data"]["object"]
        meta = data.get("metadata") or {}
        tenant_id = meta.get("tenant_id")
        pack_id = meta.get("pack_id")
        payment_id = data.get("payment_intent") or data.get("id")
        credits = float(meta.get("credits_amount") or 0)

        # New paywall purchases: route through the purchase so the grant is
        # idempotent (guarded by credits_granted + ledger idempotency key).
        purchase_id = meta.get("purchase_id")
        if purchase_id:
            purchase = self.env["doorway.credit.purchase"].sudo().browse(int(purchase_id))
            if purchase.exists():
                purchase._grant_credits(stripe_payment_id=payment_id)
                return True

        tenant = self.env["doorway.tenant"].sudo().browse(int(tenant_id)) if tenant_id else False
        if not tenant or not tenant.credit_account_id:
            return False
        pack = self.env["doorway.credit.pack"].browse(int(pack_id)) if pack_id else False
        if pack:
            credits = pack.credits_amount
            tenant.last_pack_purchased_amount = pack.credits_amount
        if credits <= 0:
            return False
        tenant.credit_account_id.credit(
            credits, pack_id=pack.id if pack else False, stripe_payment_id=payment_id
        )
        return True

    def handle_subscription_updated(self, event):
        data = event["data"]["object"]
        sub_id = data.get("id")
        sub = self.env["doorway.subscription"].sudo().search(
            [("stripe_subscription_id", "=", sub_id)], limit=1
        )
        if sub:
            status_map = {
                "active": "active",
                "past_due": "past_due",
                "canceled": "cancelled",
                "trialing": "trialing",
            }
            sub.write({"status": status_map.get(data.get("status"), "active")})
            sub.tenant_id.write(
                {"status": "active" if data.get("status") == "active" else sub.tenant_id.status}
            )
        return True

    def handle_invoice_paid(self, event):
        data = event["data"]["object"]
        customer = data.get("customer")
        tenant = self.env["doorway.tenant"].sudo().search(
            [("stripe_customer_id", "=", customer)], limit=1
        )
        if tenant:
            tenant.write({"status": "active", "payment_failure_count": 0})
        return True

    def handle_payment_failed(self, event):
        data = event["data"]["object"]
        customer = data.get("customer")
        tenant = self.env["doorway.tenant"].sudo().search(
            [("stripe_customer_id", "=", customer)], limit=1
        )
        if not tenant:
            return False
        tenant.payment_failure_count += 1
        self.env["doorway.credit.alert"].sudo().create(
            {
                "tenant_id": tenant.id,
                "alert_type": "payment_failed",
                "message": _("Échec de paiement Stripe (#%s)") % tenant.payment_failure_count,
                "severity": "critical",
            }
        )
        if tenant.payment_failure_count >= 3:
            tenant.write({"status": "suspended"})
        return True

    def handle_subscription_deleted(self, event):
        data = event["data"]["object"]
        sub_id = data.get("id")
        sub = self.env["doorway.subscription"].sudo().search(
            [("stripe_subscription_id", "=", sub_id)], limit=1
        )
        if sub:
            sub.write({"status": "cancelled"})
            sub.tenant_id.write({"status": "cancelled"})
        return True
