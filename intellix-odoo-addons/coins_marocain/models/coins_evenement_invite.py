# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsEvenementInvite(models.Model):
    _name = "coins.evenement.invite"
    _description = "Invité / RSVP événement"
    _order = "name, id"

    evenement_id = fields.Many2one(
        "coins.evenement",
        string="Événement",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Nom", required=True)
    phone = fields.Char(string="Téléphone / WhatsApp")
    email = fields.Char(string="Email")
    source = fields.Selection(
        [
            ("karine", "Invité par Karine"),
            ("zakaria", "Invité par Zakaria"),
            ("other", "Autre"),
        ],
        string="Source",
        default="karine",
        required=True,
    )
    rsvp_state = fields.Selection(
        [
            ("invited", "Invité"),
            ("confirmed", "Confirmé"),
            ("declined", "Décliné"),
            ("present", "Présent le jour-J"),
        ],
        string="RSVP",
        default="invited",
        required=True,
    )
    currency_id = fields.Many2one(
        related="evenement_id.currency_id", readonly=True
    )
    ticket_amount = fields.Monetary(
        string="Montant payé", currency_field="currency_id", default=0
    )
    payment_status = fields.Selection(
        [
            ("na", "N/A"),
            ("unpaid", "Non payé"),
            ("partial", "Partiel"),
            ("paid", "Payé"),
        ],
        string="Paiement",
        default="na",
    )
    invitation_sent = fields.Boolean(
        string="Invitation envoyée", default=False, copy=False
    )
    invitation_sent_at = fields.Datetime(string="Invitation envoyée le", copy=False)
    reminder_sent = fields.Boolean(
        string="Rappel J-1 envoyé", default=False, copy=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._maybe_send_invitation()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("rsvp_state") == "invited" or vals.get("phone"):
            self.filtered(lambda r: not r.invitation_sent)._maybe_send_invitation()
        return res

    def _maybe_send_invitation(self):
        from odoo.addons.coins_marocain.services.evenement_service import (
            CoinsEvenementService,
        )

        service = CoinsEvenementService(self.env)
        for rec in self:
            if rec.invitation_sent or not rec.phone or rec.rsvp_state != "invited":
                continue
            if rec.evenement_id.state in ("draft", "cancelled"):
                continue
            if service.send_invitation(rec):
                rec.write(
                    {
                        "invitation_sent": True,
                        "invitation_sent_at": fields.Datetime.now(),
                    }
                )
