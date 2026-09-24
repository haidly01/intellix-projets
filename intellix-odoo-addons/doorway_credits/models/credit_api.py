# -*- coding: utf-8 -*-
"""Generic, reusable credit / paywall API.

This is the single public entry point that *any* feature module can call to
gate a paid action behind a credit balance:

    api = env["doorway.credit.api"]
    if not api.has_credits(company, cost):
        return api.action_open_paywall(company, required=cost, ...)
    api.consume(company, cost, "Publication site", ref="brief:42",
                service="site_publish", idempotency_key="site_publish:brief:42")

It is intentionally decoupled from the builders: today it gates the website
and email builders, tomorrow the same calls will gate ``doorway_seo`` and the
social-media module without any change here.

Wallet scope
------------
The wallet is **company-level**. Internally it reuses the existing
``doorway.tenant`` / ``doorway.credit.account`` infrastructure (one account per
company, balance expressed in credit units). A tenant + account is
auto-provisioned on first use so the API never fails for a company that was
created after install.
"""
import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class DoorwayCreditApi(models.AbstractModel):
    _name = "doorway.credit.api"
    _description = "API crédits Doorway (paywall générique)"

    # ------------------------------------------------------------------
    # Wallet resolution
    # ------------------------------------------------------------------
    @api.model
    def _resolve_company(self, company=None):
        if company is None:
            return self.env.company
        if isinstance(company, int):
            return self.env["res.company"].sudo().browse(company)
        return company

    @api.model
    def _get_account(self, company=None, create=True):
        """Return the ``doorway.credit.account`` for ``company`` (auto-provision)."""
        company = self._resolve_company(company)
        Tenant = self.env["doorway.tenant"].sudo()
        Account = self.env["doorway.credit.account"].sudo()
        if not company:
            return Account
        tenant = Tenant.search([("company_id", "=", company.id)], limit=1)
        if not tenant:
            if not create:
                return Account
            tenant = Tenant.create(
                {
                    "name": company.name or company.display_name,
                    "company_id": company.id,
                    "email_admin": company.email or "",
                    "status": "active",
                }
            )
        if not tenant.credit_account_id:
            if not create:
                return Account
            account = Account.create({"tenant_id": tenant.id})
            tenant.credit_account_id = account.id
        return tenant.credit_account_id

    @api.model
    def _get_tenant(self, company=None, create=True):
        account = self._get_account(company, create=create)
        return account.tenant_id if account else self.env["doorway.tenant"].sudo()

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    @api.model
    def get_cost(self, param_key, default=1.0):
        """Read a cost-per-action from ``ir.config_parameter`` with a default."""
        icp = self.env["ir.config_parameter"].sudo()
        try:
            return float(icp.get_param(param_key, default))
        except (TypeError, ValueError):
            return float(default)

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------
    @api.model
    def get_balance(self, company=None):
        """Current credit balance for the company (0.0 if no wallet yet)."""
        account = self._get_account(company, create=False)
        return account.balance if account else 0.0

    @api.model
    def has_credits(self, company, amount):
        """True if the company can afford ``amount`` credits."""
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return True
        return self.get_balance(company) >= amount

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------
    @api.model
    def consume(self, company, amount, reason, ref=False, service=False, idempotency_key=None):
        """Atomically debit ``amount`` credits from the company wallet.

        Idempotent: a given ``idempotency_key`` (or ``service``/``ref`` pair) is
        only ever charged once — safe to call again on retries.

        :returns: dict ``{success, balance, required, transaction, duplicate, reason}``.
                  ``success=False`` (never an exception) when the balance is
                  insufficient, so callers can open the paywall instead.
        """
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0
        account = self._get_account(company)
        Tx = self.env["doorway.credit.transaction"].sudo()

        key = idempotency_key
        if not key and ref:
            key = "consume:%s:%s" % (service or "generic", ref)

        if key:
            dup = Tx.search(
                [("idempotency_key", "=", key), ("transaction_type", "=", "consumption")],
                limit=1,
            )
            if dup:
                return {
                    "success": True,
                    "duplicate": True,
                    "balance": account.balance if account else 0.0,
                    "transaction": dup,
                    "required": amount,
                }

        if amount <= 0:
            return {"success": True, "balance": account.balance if account else 0.0, "required": 0.0}

        if not account:
            # No wallet resolvable (no company): fail closed but cleanly.
            return {"success": False, "reason": "no_wallet", "balance": 0.0, "required": amount}

        # Serialize concurrent consumes on the same wallet to avoid double-charge.
        try:
            self.env.cr.execute(
                "SELECT id FROM doorway_credit_account WHERE id = %s FOR UPDATE", (account.id,)
            )
        except Exception:  # noqa: BLE001
            pass

        if account.balance < amount:
            return {
                "success": False,
                "reason": "insufficient",
                "balance": account.balance,
                "required": amount,
            }

        tx = account.debit(
            amount,
            service or False,
            reason or _("Consommation de crédits"),
            tx_extra={"idempotency_key": key, "ref_document": ref or False},
        )
        if not tx:
            return {
                "success": False,
                "reason": "debit_failed",
                "balance": account.balance,
                "required": amount,
            }
        return {"success": True, "balance": account.balance, "required": amount, "transaction": tx}

    @api.model
    def grant(
        self,
        company,
        amount,
        reason,
        ref=False,
        transaction_type="grant",
        idempotency_key=None,
        pack_id=None,
        stripe_payment_id=None,
        purchase_id=None,
    ):
        """Credit ``amount`` credits to the company wallet (idempotent)."""
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return False
        account = self._get_account(company)
        if not account:
            return False
        return account.credit(
            amount,
            pack_id=pack_id,
            stripe_payment_id=stripe_payment_id,
            transaction_type=transaction_type,
            description=reason,
            idempotency_key=idempotency_key,
            ref_document=ref or False,
            purchase_id=purchase_id,
        )

    # ------------------------------------------------------------------
    # Paywall action
    # ------------------------------------------------------------------
    @api.model
    def action_open_paywall(self, company=None, required=0.0, message=None, service=None):
        """Return an action opening the "insufficient balance" paywall wizard."""
        company = self._resolve_company(company)
        balance = self.get_balance(company)
        try:
            required = float(required)
        except (TypeError, ValueError):
            required = 0.0
        Pack = self.env["doorway.credit.pack"].sudo()
        pack = Pack.search(
            [("is_active", "=", True), ("credits_amount", ">=", required)],
            order="credits_amount",
            limit=1,
        ) or Pack.search([("is_active", "=", True)], order="credits_amount", limit=1)
        methods = self.env["doorway.credit.purchase"].available_methods()
        vals = {
            "company_id": company.id if company else False,
            "balance_credits": balance,
            "required_credits": required,
            "service": service or False,
            "custom_message": message or False,
        }
        if pack:
            vals["pack_id"] = pack.id
        if methods:
            vals["payment_method"] = methods[0]
        wizard = self.env["doorway.credit.paywall"].sudo().create(vals)
        return {
            "type": "ir.actions.act_window",
            "name": _("Solde insuffisant"),
            "res_model": "doorway.credit.paywall",
            "view_mode": "form",
            "target": "new",
            "res_id": wizard.id,
        }
