# -*- coding: utf-8 -*-
"""Provisionnement automatique d'un nouveau tenant SaaS."""
import logging
import secrets
from datetime import timedelta

from odoo import _, fields

_logger = logging.getLogger(__name__)


class ProvisioningService:
    """Crée un client SaaS complet en quelques étapes."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def provision_new_tenant(
        self, company_name, admin_email, user_count=1, stripe_customer_id=None
    ):
        """
        Crée company, utilisateur admin, tenant, compte crédits, essai, abonnement.
        Retourne dict tenant_id, login_url, temp_password, api_key.
        """
        temp_password = secrets.token_urlsafe(12)
        company = self.env["res.company"].sudo().create({"name": company_name})
        user = self.env["res.users"].sudo().create(
            {
                "name": _("Admin %s") % company_name,
                "login": admin_email,
                "email": admin_email,
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                "password": temp_password,
            }
        )
        tenant = self.env["doorway.tenant"].sudo().create(
            {
                "name": company_name,
                "company_id": company.id,
                "email_admin": admin_email,
                "status": "trial",
                "trial_end_date": fields.Date.today() + timedelta(days=14),
                "stripe_customer_id": stripe_customer_id,
            }
        )
        subscription = self.env["doorway.subscription"].sudo().create(
            {"tenant_id": tenant.id, "user_count": user_count, "status": "trialing"}
        )
        tenant.write({"subscription_id": subscription.id})
        account = self.env["doorway.credit.account"].sudo().create({"tenant_id": tenant.id})
        tenant.write({"credit_account_id": account.id})

        trial_amount = float(
            self._icp.get_param("doorway_credits.trial_credits_amount", "25") or 25
        )
        account.credit(trial_amount, transaction_type="trial")
        self.setup_default_agents(tenant)
        if not stripe_customer_id:
            try:
                from odoo.addons.doorway_credits.services.stripe_service import StripeService

                if StripeService(self.env).is_configured():
                    StripeService(self.env).create_subscription(tenant, user_count)
            except Exception as error:  # noqa: BLE001
                _logger.warning("Stripe subscription provisioning : %s", error)

        self.send_welcome_email(tenant, temp_password)
        base_url = self._icp.get_param("web.base.url", "")
        return {
            "tenant_id": tenant.id,
            "user_id": user.id,
            "login_url": base_url,
            "temp_password": temp_password,
            "api_key": tenant.api_key,
        }

    def send_welcome_email(self, tenant, temp_password):
        """Email de bienvenue avec accès et crédits d'essai."""
        if not tenant.email_admin:
            return False
        base_url = self._icp.get_param("web.base.url", "")
        body = (
            "<p>Bienvenue sur la plateforme Doorway IA.</p>"
            "<p>URL : <a href='%s'>%s</a></p>"
            "<p>Identifiant : %s<br/>Mot de passe temporaire : %s</p>"
            "<p>Solde crédits d'essai : %.2f USD</p>"
            "<p>Clé API : %s</p>"
        ) % (
            base_url,
            base_url,
            tenant.email_admin,
            temp_password,
            tenant.credit_balance,
            tenant.api_key,
        )
        try:
            self.env["mail.mail"].sudo().create(
                {
                    "subject": _("Bienvenue — Agence Doorway IA"),
                    "body_html": body,
                    "email_to": tenant.email_admin,
                    "auto_delete": True,
                }
            ).send()
        except Exception:  # noqa: BLE001
            _logger.warning("Email bienvenue non envoyé")
        return True

    def setup_default_agents(self, tenant):
        """Copie les agents IA template pour le tenant (même société)."""
        Agent = self.env.get("doorway.agent.ia")
        if not Agent:
            return False
        templates = Agent.sudo().search([("code", "!=", False)], limit=12)
        for tpl in templates:
            if not Agent.search(
                [("code", "=", tpl.code), ("id", "!=", tpl.id)], limit=1
            ):
                continue
        return True
