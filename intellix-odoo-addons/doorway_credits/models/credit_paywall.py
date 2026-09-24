# -*- coding: utf-8 -*-
"""Reusable paywall dialog: "Solde insuffisant — achetez un pack".

Opened by ``doorway.credit.api.action_open_paywall(...)`` whenever a gated
action (site publish, email send, …) is blocked for lack of credits. It lets
the user pick a pack + a payment method and launches the purchase.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayCreditPaywall(models.TransientModel):
    _name = "doorway.credit.paywall"
    _description = "Paywall crédits"

    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True
    )
    balance_credits = fields.Float(string="Solde actuel", readonly=True)
    required_credits = fields.Float(string="Crédits requis", readonly=True)
    service = fields.Char(readonly=True)
    custom_message = fields.Char(readonly=True)
    message = fields.Html(compute="_compute_message")

    pack_id = fields.Many2one(
        "doorway.credit.pack",
        string="Pack à acheter",
        domain=[("is_active", "=", True)],
    )
    payment_method = fields.Selection(
        [
            ("stripe", "Carte bancaire (Stripe)"),
            ("interac", "Virement Interac"),
            ("rib", "Virement bancaire / RIB"),
        ],
        string="Mode de paiement",
        default="stripe",
    )
    available_methods = fields.Char(compute="_compute_available_methods")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        Pack = self.env["doorway.credit.pack"].sudo()
        required = res.get("required_credits") or 0.0
        pack = Pack.search(
            [("is_active", "=", True), ("credits_amount", ">=", required)],
            order="credits_amount",
            limit=1,
        ) or Pack.search([("is_active", "=", True)], order="credits_amount", limit=1)
        if pack and not res.get("pack_id"):
            res["pack_id"] = pack.id
        methods = self.env["doorway.credit.purchase"].available_methods()
        if methods and res.get("payment_method") not in methods:
            res["payment_method"] = methods[0]
        if "balance_credits" in fields_list and not res.get("balance_credits"):
            company = self.env["res.company"].browse(res.get("company_id")) if res.get("company_id") else self.env.company
            res["balance_credits"] = self.env["doorway.credit.api"].get_balance(company)
        return res

    @api.depends("company_id")
    def _compute_available_methods(self):
        methods = ",".join(self.env["doorway.credit.purchase"].available_methods())
        for rec in self:
            rec.available_methods = methods

    @api.depends("balance_credits", "required_credits", "custom_message")
    def _compute_message(self):
        for rec in self:
            if rec.custom_message:
                body = "<p>%s</p>" % rec.custom_message
            else:
                body = _(
                    "<p><b>Solde insuffisant pour publier.</b></p>"
                    "<p>Cette action consomme <b>%(req).0f</b> crédit(s) et votre "
                    "solde est de <b>%(bal).0f</b>. Achetez un pack pour continuer "
                    "— la génération et la prévisualisation restent gratuites.</p>"
                ) % {"req": rec.required_credits or 0.0, "bal": rec.balance_credits or 0.0}
            if not self.env["doorway.credit.purchase"].available_methods():
                body += _(
                    "<p class='text-warning'>Aucun mode de paiement n'est encore configuré. "
                    "Contactez l'administrateur (Stripe / Interac / RIB à paramétrer).</p>"
                )
            rec.message = body

    def action_buy(self):
        """Create the purchase for the chosen pack + method and launch payment."""
        self.ensure_one()
        if not self.pack_id:
            raise UserError(_("Veuillez choisir un pack."))
        if not self.payment_method:
            raise UserError(_("Veuillez choisir un mode de paiement."))
        purchase = self.env["doorway.credit.purchase"].create(
            {
                "company_id": self.company_id.id,
                "pack_id": self.pack_id.id,
                "payment_method": self.payment_method,
                "partner_id": self.env.user.partner_id.id,
            }
        )
        return purchase.action_pay()
