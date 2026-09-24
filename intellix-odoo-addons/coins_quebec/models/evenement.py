# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CoinsQuebecEvenement(models.Model):
    _name = "coins.quebec.evenement"
    _description = "Événement (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(string="Nom de l'événement", required=True, tracking=True)
    reference = fields.Char(
        required=True, copy=False, default=lambda self: _("Nouveau")
    )
    active = fields.Boolean(default=True)
    event_type = fields.Selection(
        [
            ("pilote", "Pilote"),
            ("mariage", "Mariage"),
            ("soiree_recurrente", "Soirée récurrente"),
            ("privatisation", "Privatisation"),
            ("other", "Autre"),
        ],
        default="pilote",
        required=True,
        tracking=True,
    )
    date_start = fields.Datetime(string="Début", required=True, tracking=True)
    date_end = fields.Datetime(string="Fin")
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirmé"),
            ("done", "Terminé"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    property_id = fields.Many2one("coins.quebec.property", string="Lieu")
    partner_id = fields.Many2one("res.partner", string="Client")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id, required=True
    )
    amount = fields.Monetary(string="Montant HT", currency_field="currency_id")
    amount_tax = fields.Monetary(string="TPS / TVQ", currency_field="currency_id")
    notes = fields.Text()

    @api.onchange("amount")
    def _onchange_tax(self):
        self.amount_tax = round((self.amount or 0) * 0.14975, 2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("reference") or vals.get("reference") == _("Nouveau"):
                vals["reference"] = self.env["ir.sequence"].next_by_code(
                    "coins.quebec.evenement"
                ) or _("CQ-EVT")
        return super().create(vals_list)
