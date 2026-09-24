# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class DoorwayCreditTransaction(models.Model):
    _name = "doorway.credit.transaction"
    _description = "Transaction de crédits (append-only)"
    _order = "date desc, id desc"

    account_id = fields.Many2one(
        "doorway.credit.account", required=True, ondelete="restrict", index=True
    )
    tenant_id = fields.Many2one(related="account_id.tenant_id", store=True, index=True)
    transaction_type = fields.Selection(
        [
            ("purchase", "Achat de crédits"),
            ("consumption", "Consommation IA"),
            ("bonus", "Bonus pack"),
            ("grant", "Crédits offerts (admin)"),
            ("refund", "Remboursement"),
            ("trial", "Crédits d'essai"),
        ],
        required=True,
    )
    service = fields.Selection(
        [
            ("claude_analysis", "Analyse Claude (appel)"),
            ("claude_report", "Rapport post-appel Claude"),
            ("elevenlabs_voice", "ElevenLabs (minute vocale)"),
            ("twilio_call", "Twilio (minute appel)"),
            ("twilio_sms", "Twilio (SMS)"),
            ("n8n_workflow", "Workflow n8n"),
            ("sofia_es_call", "Sofia ES — appel vocal"),
            ("site_publish", "Publication site web (Site Builder)"),
            ("email_send", "Envoi mailing (Email Builder)"),
            ("seo_publish", "Publication SEO"),
            ("social_publish", "Publication réseaux sociaux"),
        ],
    )
    call_sid = fields.Char(string="Call SID", index=True)
    duration_seconds = fields.Integer(string="Durée (s)")
    cost_euros = fields.Float(string="Coût EUR", digits=(16, 4))
    amd_result = fields.Selection(
        [
            ("human", "Humain"),
            ("machine", "Répondeur"),
            ("not_sure", "Incertain"),
            ("unknown", "Inconnu"),
        ],
        string="AMD",
    )
    campaign_ref = fields.Char(string="Campagne")
    amount = fields.Float(digits=(16, 2), help="Positif = crédit, négatif = débit")
    balance_after = fields.Float(digits=(16, 2))
    description = fields.Char()
    date = fields.Datetime(default=fields.Datetime.now, index=True)
    call_session_id = fields.Many2one("doorway.call.session", ondelete="set null")
    stripe_payment_id = fields.Char(index=True)
    pack_id = fields.Many2one("doorway.credit.pack", ondelete="set null")
    real_cost = fields.Float(digits=(16, 4))
    charged_amount = fields.Float(digits=(16, 4))
    # Generic paywall layer: idempotency + free-form document reference so the
    # same publish/send/purchase is never charged or granted twice on retries.
    idempotency_key = fields.Char(index=True, copy=False)
    ref_document = fields.Char(string="Document lié")
    purchase_id = fields.Many2one("doorway.credit.purchase", ondelete="set null", index=True)
    margin = fields.Float(compute="_compute_margin", store=True, digits=(16, 4))

    @api.depends("charged_amount", "real_cost", "amount")
    def _compute_margin(self):
        for rec in self:
            if rec.transaction_type == "consumption" and rec.charged_amount:
                rec.margin = rec.charged_amount - (rec.real_cost or 0)
            else:
                rec.margin = 0.0

    def write(self, vals):
        """Append-only : aucune modification des transactions."""
        protected = {
            "amount",
            "balance_after",
            "transaction_type",
            "account_id",
            "service",
            "stripe_payment_id",
        }
        if protected & set(vals.keys()):
            from odoo.exceptions import UserError

            raise UserError(_("Les transactions de crédits sont immuables (audit)."))
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import UserError

        raise UserError(_("Les transactions de crédits ne peuvent pas être supprimées."))
