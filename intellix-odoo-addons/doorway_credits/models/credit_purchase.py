# -*- coding: utf-8 -*-
"""Credit pack purchase order with three payment methods.

* ``stripe``  — online card payment (automated). Uses the existing Stripe
  integration (live API keys). On confirmed payment (Stripe webhook), the
  pack's credits are granted automatically and idempotently.
* ``interac`` — Interac e-transfer (Canada / Québec). Offline: the buyer is
  shown a configurable recipient email + the unique purchase reference; the
  purchase stays "paiement en attente" until an admin confirms reception.
* ``rib``     — bank transfer / SEPA (France). Offline: the buyer is shown
  configurable IBAN/BIC/beneficiary + the unique reference; admin confirms.

Every grant is guarded by ``credits_granted`` and routed through an idempotent
ledger key, so credits are granted **exactly once** per purchase no matter how
many times the webhook fires or the admin clicks "Confirmer".
"""
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAM_INTERAC_EMAIL = "doorway_credits.interac_email"
PARAM_RIB_IBAN = "doorway_credits.rib_iban"
PARAM_RIB_BIC = "doorway_credits.rib_bic"
PARAM_RIB_BENEFICIARY = "doorway_credits.rib_beneficiary"


class DoorwayCreditPurchase(models.Model):
    _name = "doorway.credit.purchase"
    _description = "Achat de pack de crédits"
    _inherit = ["mail.thread"]
    _order = "create_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True, default="Nouveau", index=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    partner_id = fields.Many2one(
        "res.partner", string="Client", default=lambda self: self.env.user.partner_id
    )
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    pack_id = fields.Many2one("doorway.credit.pack", string="Pack", required=True)
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.ref("base.USD", raise_if_not_found=False),
    )
    amount = fields.Float(string="Montant", digits=(16, 2))
    credits = fields.Float(string="Crédits", digits=(16, 2))

    payment_method = fields.Selection(
        [
            ("stripe", "Carte bancaire (Stripe)"),
            ("interac", "Virement Interac"),
            ("rib", "Virement bancaire / RIB"),
        ],
        string="Mode de paiement",
        required=True,
        default="stripe",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("pending", "Paiement en attente"),
            ("paid", "Payé"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    credits_granted = fields.Boolean(
        string="Crédits accordés", default=False, copy=False, readonly=True
    )
    transaction_id = fields.Many2one(
        "doorway.credit.transaction", string="Écriture crédits", readonly=True, copy=False
    )
    stripe_payment_id = fields.Char(readonly=True, copy=False, index=True)
    stripe_session_url = fields.Char(readonly=True, copy=False)
    date_paid = fields.Datetime(readonly=True, copy=False)
    payment_instructions = fields.Html(compute="_compute_payment_instructions")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "La référence d'achat doit être unique."),
    ]

    # ------------------------------------------------------------------
    # Defaults / onchange
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "Nouveau":
                vals["name"] = "CRD-%s" % secrets.token_hex(4).upper()
            pack = self.env["doorway.credit.pack"].browse(vals.get("pack_id"))
            if pack:
                vals.setdefault("amount", pack.price_usd)
                vals.setdefault("credits", pack.credits_amount)
        return super().create(vals_list)

    @api.onchange("pack_id")
    def _onchange_pack_id(self):
        for rec in self:
            if rec.pack_id:
                rec.amount = rec.pack_id.price_usd
                rec.credits = rec.pack_id.credits_amount

    # ------------------------------------------------------------------
    # Availability of each method (graceful degradation)
    # ------------------------------------------------------------------
    @api.model
    def _stripe_available(self):
        from odoo.addons.doorway_credits.services.stripe_service import StripeService

        if StripeService(self.env).is_configured():
            return True
        provider = (
            self.env["payment.provider"]
            .sudo()
            .search([("code", "=", "stripe"), ("state", "in", ("enabled", "test"))], limit=1)
            if "payment.provider" in self.env
            else False
        )
        return bool(provider)

    @api.model
    def _interac_available(self):
        return bool(self.env["ir.config_parameter"].sudo().get_param(PARAM_INTERAC_EMAIL))

    @api.model
    def _rib_available(self):
        return bool(self.env["ir.config_parameter"].sudo().get_param(PARAM_RIB_IBAN))

    @api.model
    def available_methods(self):
        """Return the list of currently usable payment methods (for the UI)."""
        methods = []
        if self._stripe_available():
            methods.append("stripe")
        if self._interac_available():
            methods.append("interac")
        if self._rib_available():
            methods.append("rib")
        return methods

    # ------------------------------------------------------------------
    # Instructions
    # ------------------------------------------------------------------
    @api.depends("payment_method", "name", "amount", "currency_id")
    def _compute_payment_instructions(self):
        icp = self.env["ir.config_parameter"].sudo()
        for rec in self:
            rec.payment_instructions = rec._build_instructions(icp)

    def _build_instructions(self, icp):
        ref = self.name or ""
        if self.payment_method == "stripe":
            return _(
                "<p>Vous allez être redirigé vers le paiement sécurisé Stripe. "
                "Vos crédits seront ajoutés automatiquement après confirmation du paiement.</p>"
            )
        if self.payment_method == "interac":
            email = icp.get_param(PARAM_INTERAC_EMAIL)
            if not email:
                return _(
                    "<p class='text-danger'>Le virement Interac n'est pas encore configuré "
                    "(paramètre <code>doorway_credits.interac_email</code>).</p>"
                )
            return _(
                "<div><p><b>Virement Interac</b></p>"
                "<ul>"
                "<li>Destinataire : <b>%(email)s</b></li>"
                "<li>Montant : <b>%(amount)s</b></li>"
                "<li>Message / note (obligatoire) : <b>%(ref)s</b></li>"
                "</ul>"
                "<p>Indiquez bien la référence <b>%(ref)s</b> dans le message du virement. "
                "Vos crédits seront ajoutés dès réception confirmée par notre équipe.</p></div>"
            ) % {"email": email, "amount": self._amount_label(), "ref": ref}
        if self.payment_method == "rib":
            iban = icp.get_param(PARAM_RIB_IBAN)
            if not iban:
                return _(
                    "<p class='text-danger'>Le virement bancaire (RIB/IBAN) n'est pas encore "
                    "configuré (paramètre <code>doorway_credits.rib_iban</code>).</p>"
                )
            bic = icp.get_param(PARAM_RIB_BIC) or "—"
            beneficiary = icp.get_param(PARAM_RIB_BENEFICIARY) or "—"
            return _(
                "<div><p><b>Virement bancaire (SEPA / RIB)</b></p>"
                "<ul>"
                "<li>Bénéficiaire : <b>%(beneficiary)s</b></li>"
                "<li>IBAN : <b>%(iban)s</b></li>"
                "<li>BIC : <b>%(bic)s</b></li>"
                "<li>Montant : <b>%(amount)s</b></li>"
                "<li>Référence à indiquer : <b>%(ref)s</b></li>"
                "</ul>"
                "<p>Indiquez bien la référence <b>%(ref)s</b> dans le motif du virement. "
                "Vos crédits seront ajoutés dès réception confirmée par notre équipe.</p></div>"
            ) % {
                "beneficiary": beneficiary,
                "iban": iban,
                "bic": bic,
                "amount": self._amount_label(),
                "ref": ref,
            }
        return ""

    def _amount_label(self):
        symbol = self.currency_id.symbol or (self.currency_id.name or "USD")
        return "%s %s" % (("%.2f" % (self.amount or 0.0)), symbol)

    # ------------------------------------------------------------------
    # Payment flow
    # ------------------------------------------------------------------
    def action_pay(self):
        """Start the payment for the chosen method.

        Stripe → redirect to checkout. Interac/RIB → mark pending and show
        instructions. Never crashes if a method is not configured.
        """
        self.ensure_one()
        if not self.pack_id:
            raise UserError(_("Aucun pack sélectionné."))
        if not self.amount:
            self.amount = self.pack_id.price_usd
        if not self.credits:
            self.credits = self.pack_id.credits_amount

        if self.payment_method == "stripe":
            return self._pay_stripe()
        # Offline methods: Interac / RIB
        return self._pay_offline()

    def _pay_stripe(self):
        from odoo.addons.doorway_credits.services.stripe_service import StripeService

        svc = StripeService(self.env)
        if not svc.is_configured():
            raise UserError(
                _(
                    "Le paiement par carte (Stripe) n'est pas encore configuré. "
                    "Choisissez un autre mode de paiement ou contactez l'administrateur."
                )
            )
        tenant = self.env["doorway.credit.api"]._get_tenant(self.company_id)
        if not tenant:
            raise UserError(_("Impossible de résoudre le compte crédits de la société."))
        url = svc.create_checkout_session(tenant, self.pack_id, purchase=self)
        self.write({"state": "pending", "stripe_session_url": url})
        self.message_post(body=_("Redirection vers le paiement Stripe (réf. %s).") % self.name)
        return {"type": "ir.actions.act_url", "url": url, "target": "self"}

    def _pay_offline(self):
        icp = self.env["ir.config_parameter"].sudo()
        if self.payment_method == "interac" and not self._interac_available():
            raise UserError(
                _("Le virement Interac n'est pas encore configuré. Choisissez un autre mode.")
            )
        if self.payment_method == "rib" and not self._rib_available():
            raise UserError(
                _("Le virement bancaire (RIB) n'est pas encore configuré. Choisissez un autre mode.")
            )
        self.write({"state": "pending"})
        self.message_post(
            body=_(
                "Achat %s en attente de paiement (%s). Instructions transmises au client."
            )
            % (self.name, dict(self._fields["payment_method"].selection).get(self.payment_method))
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Instructions de paiement"),
            "res_model": "doorway.credit.purchase",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Confirmation / grant (idempotent)
    # ------------------------------------------------------------------
    def action_confirm_payment(self):
        """Admin confirms an offline payment was received → grant credits once."""
        for rec in self:
            if rec.state == "cancelled":
                raise UserError(_("Achat annulé : impossible de confirmer."))
            rec._grant_credits(reason=_("Paiement confirmé (%s)") % rec.name)
        return True

    def action_cancel(self):
        for rec in self:
            if rec.credits_granted:
                raise UserError(_("Crédits déjà accordés : impossible d'annuler."))
            rec.state = "cancelled"
        return True

    def action_view_self(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.credit.purchase",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def _grant_credits(self, reason=None, stripe_payment_id=None):
        """Grant the pack credits to the company wallet — exactly once."""
        self.ensure_one()
        if self.credits_granted or self.state == "paid":
            return self.transaction_id
        if stripe_payment_id and not self.stripe_payment_id:
            self.stripe_payment_id = stripe_payment_id
        credits = self.credits or (self.pack_id.credits_amount if self.pack_id else 0.0)
        if credits <= 0:
            return False
        api = self.env["doorway.credit.api"]
        tx = api.grant(
            self.company_id,
            credits,
            reason or (_("Achat pack %s") % (self.pack_id.name or self.name)),
            ref=self.name,
            transaction_type="purchase",
            idempotency_key="purchase:%s" % self.name,
            pack_id=self.pack_id.id if self.pack_id else None,
            stripe_payment_id=self.stripe_payment_id or None,
            purchase_id=self.id,
        )
        vals = {"state": "paid", "credits_granted": True, "date_paid": fields.Datetime.now()}
        if tx:
            vals["transaction_id"] = tx.id
            tenant = self.env["doorway.credit.api"]._get_tenant(self.company_id)
            if tenant and self.pack_id:
                tenant.sudo().last_pack_purchased_amount = self.pack_id.credits_amount
        self.write(vals)
        self.message_post(body=_("Crédits accordés : %.2f (réf. %s).") % (credits, self.name))
        return tx
