# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayCreditAccount(models.Model):
    _name = "doorway.credit.account"
    _description = "Compte de crédits IA"
    _rec_name = "tenant_id"

    tenant_id = fields.Many2one("doorway.tenant", required=True, ondelete="cascade", index=True)
    balance = fields.Float(string="Solde USD", default=0.0, digits=(16, 2))
    total_purchased = fields.Float(digits=(16, 2), default=0.0)
    total_consumed = fields.Float(digits=(16, 2), default=0.0)
    total_transactions = fields.Integer(default=0)
    current_month_consumption = fields.Float(
        compute="_compute_period_consumption", digits=(16, 2)
    )
    today_consumption = fields.Float(compute="_compute_period_consumption", digits=(16, 2))
    transaction_ids = fields.One2many("doorway.credit.transaction", "account_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.ref("base.USD", raise_if_not_found=False),
    )

    def _compute_period_consumption(self):
        Transaction = self.env["doorway.credit.transaction"]
        today_start = fields.Datetime.to_string(
            datetime.combine(fields.Date.today(), datetime.min.time())
        )
        month_start = fields.Datetime.to_string(
            datetime.combine(
                fields.Date.today().replace(day=1), datetime.min.time()
            )
        )
        for rec in self:
            rec.today_consumption = abs(
                sum(
                    Transaction.search(
                        [
                            ("account_id", "=", rec.id),
                            ("transaction_type", "=", "consumption"),
                            ("date", ">=", today_start),
                        ]
                    ).mapped("amount")
                )
            )
            rec.current_month_consumption = abs(
                sum(
                    Transaction.search(
                        [
                            ("account_id", "=", rec.id),
                            ("transaction_type", "=", "consumption"),
                            ("date", ">=", month_start),
                        ]
                    ).mapped("amount")
                )
            )

    def debit(self, amount, service, description, call_session_id=None, real_cost=None, tx_extra=None):
        """
        Débite le compte. amount doit être positif (sera enregistré négatif).
        Retourne la transaction créée ou False.
        """
        self.ensure_one()
        tenant = self.tenant_id
        if tenant.status not in ("trial", "active"):
            raise UserError(_("Compte suspendu ou inactif."))
        if amount <= 0:
            return False
        if self.today_consumption + amount > tenant.daily_credit_limit:
            raise UserError(_("Plafond journalier de crédits atteint."))
        if self.balance < amount:
            return False
        pricing = self.env["doorway.ai.pricing"].get_pricing(service)
        charged = round(amount, 2)
        real = real_cost if real_cost is not None else (pricing["real_cost"] if pricing else 0)
        client = pricing["client_price"] if pricing else charged

        new_balance = round(self.balance - charged, 2)
        self.write(
            {
                "balance": new_balance,
                "total_consumed": self.total_consumed + charged,
                "total_transactions": self.total_transactions + 1,
            }
        )
        tx_vals = {
            "account_id": self.id,
            "transaction_type": "consumption",
            "service": service,
            "amount": -charged,
            "balance_after": new_balance,
            "description": description,
            "call_session_id": call_session_id,
            "real_cost": real,
            "charged_amount": client,
        }
        if tx_extra:
            tx_vals.update(tx_extra)
        tx = self.env["doorway.credit.transaction"].sudo().create(tx_vals)
        tenant._check_low_balance_alert()
        tenant._maybe_auto_recharge()
        return tx

    def credit(
        self,
        amount,
        pack_id=None,
        stripe_payment_id=None,
        transaction_type="purchase",
        description=None,
        idempotency_key=None,
        ref_document=None,
        purchase_id=None,
    ):
        """Crédite le compte après paiement confirmé.

        Idempotent : si ``stripe_payment_id`` OU ``idempotency_key`` correspond à
        une transaction déjà enregistrée, on retourne celle-ci sans re-créditer.
        """
        self.ensure_one()
        if amount <= 0:
            return False
        Tx = self.env["doorway.credit.transaction"].sudo()
        if stripe_payment_id:
            existing = Tx.search([("stripe_payment_id", "=", stripe_payment_id)], limit=1)
            if existing:
                return existing
        if idempotency_key:
            existing = Tx.search([("idempotency_key", "=", idempotency_key)], limit=1)
            if existing:
                return existing
        new_balance = round(self.balance + amount, 2)
        self.write(
            {
                "balance": new_balance,
                "total_purchased": self.total_purchased + amount,
                "total_transactions": self.total_transactions + 1,
            }
        )
        return Tx.create(
            {
                "account_id": self.id,
                "transaction_type": transaction_type,
                "amount": amount,
                "balance_after": new_balance,
                "description": description or _("Recharge crédits"),
                "pack_id": pack_id,
                "stripe_payment_id": stripe_payment_id,
                "idempotency_key": idempotency_key,
                "ref_document": ref_document,
                "purchase_id": purchase_id,
            }
        )
