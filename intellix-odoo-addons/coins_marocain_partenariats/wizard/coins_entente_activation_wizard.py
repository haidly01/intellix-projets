# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsEntenteActivationWizard(models.TransientModel):
    _name = "coins.entente.activation.wizard"
    _description = "Wizard — enregistrer une activation d'entente"

    entente_id = fields.Many2one(
        "coins.entente",
        string="Entente",
        required=True,
    )
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
    )
    montant = fields.Monetary(
        string="Montant de la vente",
        currency_field="currency_id",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    note = fields.Char(string="Note")

    def action_confirm(self):
        self.ensure_one()
        self.env["coins.entente.activation"].create(
            {
                "entente_id": self.entente_id.id,
                "date": self.date,
                "montant": self.montant,
                "note": self.note,
            }
        )
        return {"type": "ir.actions.act_window_close"}
