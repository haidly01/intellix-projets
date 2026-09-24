# -*- coding: utf-8 -*-
import secrets
from datetime import timedelta

from odoo import _, api, fields, models


class DoorwayTenant(models.Model):
    _name = "doorway.tenant"
    _description = "Client SaaS Doorway"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, ondelete="restrict")
    email_admin = fields.Char()
    phone = fields.Char()
    api_key = fields.Char(
        string="Clé API",
        copy=False,
        default=lambda self: secrets.token_urlsafe(32),
        groups="doorway_credits.group_doorway_credits_admin",
    )
    subscription_id = fields.Many2one("doorway.subscription", ondelete="set null")
    user_count = fields.Integer(compute="_compute_user_count")
    monthly_fee = fields.Float(compute="_compute_monthly_fee", digits=(16, 2))
    credit_account_id = fields.Many2one("doorway.credit.account", ondelete="restrict")
    credit_balance = fields.Float(related="credit_account_id.balance")
    current_month_consumption = fields.Float(
        related="credit_account_id.current_month_consumption"
    )
    today_consumption = fields.Float(related="credit_account_id.today_consumption")
    status = fields.Selection(
        [
            ("trial", "Essai gratuit"),
            ("active", "Actif"),
            ("suspended", "Suspendu"),
            ("cancelled", "Annulé"),
        ],
        default="trial",
        tracking=True,
    )
    trial_end_date = fields.Date()
    stripe_customer_id = fields.Char(index=True)
    stripe_subscription_id = fields.Char(related="subscription_id.stripe_subscription_id")
    daily_credit_limit = fields.Float(default=200.0)
    auto_recharge = fields.Boolean(default=False)
    auto_recharge_threshold = fields.Float(default=20.0)
    auto_recharge_amount = fields.Float(default=50.0)
    last_pack_purchased_amount = fields.Float(
        help="Montant du dernier pack acheté (pour alerte 20%)"
    )
    payment_failure_count = fields.Integer(default=0)
    transaction_ids = fields.One2many(
        "doorway.credit.transaction", "tenant_id", string="Transactions"
    )
    alert_ids = fields.One2many("doorway.credit.alert", "tenant_id")

    @api.depends("company_id")
    def _compute_user_count(self):
        for rec in self:
            if rec.company_id:
                rec.user_count = self.env["res.users"].search_count(
                    [("company_id", "=", rec.company_id.id), ("share", "=", False)]
                )
            else:
                rec.user_count = 0

    @api.depends("subscription_id.monthly_total", "user_count")
    def _compute_monthly_fee(self):
        for rec in self:
            if rec.subscription_id:
                rec.monthly_fee = rec.subscription_id.monthly_total
            else:
                rec.monthly_fee = rec.user_count * 89.0

    def _check_low_balance_alert(self):
        """Alerte si solde < 20% du dernier pack acheté."""
        for rec in self:
            threshold = rec.last_pack_purchased_amount * 0.2 if rec.last_pack_purchased_amount else 10.0
            if rec.credit_balance < threshold:
                existing = self.env["doorway.credit.alert"].search(
                    [
                        ("tenant_id", "=", rec.id),
                        ("alert_type", "=", "low_balance"),
                        ("is_read", "=", False),
                    ],
                    limit=1,
                )
                if not existing:
                    self.env["doorway.credit.alert"].create(
                        {
                            "tenant_id": rec.id,
                            "alert_type": "low_balance",
                            "message": _("Solde bas : %.2f USD (seuil %.2f)") % (rec.credit_balance, threshold),
                            "severity": "warning",
                        }
                    )
                    rec._send_low_balance_email()

    def _send_low_balance_email(self):
        self.ensure_one()
        if not self.email_admin:
            return
        try:
            self.env["mail.mail"].sudo().create(
                {
                    "subject": _("Doorway — Solde crédits bas"),
                    "body_html": "<p>Votre solde crédits IA est de <b>%.2f USD</b>.</p>" % self.credit_balance,
                    "email_to": self.email_admin,
                    "auto_delete": True,
                }
            ).send()
        except Exception:  # noqa: BLE001
            pass

    def _maybe_auto_recharge(self):
        for rec in self.filtered(lambda t: t.auto_recharge and t.stripe_customer_id):
            if rec.credit_balance < rec.auto_recharge_threshold:
                from odoo.addons.doorway_credits.services.stripe_service import StripeService

                StripeService(rec.env).charge_auto_recharge(rec)

    def action_open_checkout_pack(self, pack_id):
        """Ouvre Stripe Checkout pour un pack."""
        self.ensure_one()
        pack = self.env["doorway.credit.pack"].browse(pack_id)
        from odoo.addons.doorway_credits.services.stripe_service import StripeService

        url = StripeService(self.env).create_checkout_session(self, pack)
        return {"type": "ir.actions.act_url", "url": url, "target": "self"}

    def action_buy_pack_starter(self):
        return self.action_open_checkout_pack(self.env.ref("doorway_credits.pack_starter").id)

    def action_buy_pack_pro(self):
        return self.action_open_checkout_pack(self.env.ref("doorway_credits.pack_pro").id)

    def action_buy_pack_agence(self):
        return self.action_open_checkout_pack(self.env.ref("doorway_credits.pack_agence").id)

    @api.model_create_multi
    def create(self, vals_list):
        tenants = super().create(vals_list)
        Account = self.env["doorway.credit.account"].sudo()
        for tenant in tenants:
            if not tenant.credit_account_id:
                account = Account.create({"tenant_id": tenant.id})
                tenant.credit_account_id = account.id
        return tenants

    @api.model
    def _doorway_credits_fix_access(self):
        """Groupe tenant pour les utilisateurs internes + tenant par société."""
        group = self.env.ref(
            "doorway_credits.group_doorway_credits_tenant", raise_if_not_found=False
        )
        if group:
            users = self.env["res.users"].search([("share", "=", False)])
            for user in users:
                if group not in user.group_ids:
                    user.write({"group_ids": [(4, group.id)]})

        icp = self.env["ir.config_parameter"].sudo()
        trial = float(icp.get_param("doorway_credits.trial_credits_amount", "25") or 25)
        Tenant = self.sudo()
        Account = self.env["doorway.credit.account"].sudo()
        for company in self.env["res.company"].search([]):
            tenant = Tenant.search([("company_id", "=", company.id)], limit=1)
            if not tenant:
                tenant = Tenant.create(
                    {
                        "name": company.name or company.display_name,
                        "company_id": company.id,
                        "email_admin": company.email or "",
                        "status": "active",
                    }
                )
            if not tenant.credit_account_id:
                account = Account.create({"tenant_id": tenant.id})
                tenant.credit_account_id = account.id
            if tenant.credit_account_id and trial > 0 and not tenant.transaction_ids:
                tenant.credit_account_id.credit(trial, transaction_type="trial")

    def _doorway_custom_service_price(self, service, quantity=1):
        """Surchargeable par doorway_demo_call_center (tarif forfaitaire demo)."""
        return None

    @api.model
    def get_tenant_for_company(self, company=None):
        company = company or self.env.company
        return self.sudo().search([("company_id", "=", company.id)], limit=1)

    @api.model
    def get_tenant_by_api_key(self, api_key):
        if not api_key:
            return self.browse()
        return self.sudo().search([("api_key", "=", api_key)], limit=1)
