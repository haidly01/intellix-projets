# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsEntenteActivation(models.Model):
    _name = "coins.entente.activation"
    _description = "Activation / vente trackée d'une entente"
    _order = "date desc, id desc"

    entente_id = fields.Many2one(
        "coins.entente",
        string="Entente",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    montant = fields.Monetary(
        string="Montant",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    currency_id = fields.Many2one(
        related="entente_id.currency_id",
        store=True,
        readonly=True,
    )
    note = fields.Char(string="Note")
    name = fields.Char(
        string="Libellé",
        compute="_compute_name",
        store=True,
    )

    @api.depends("entente_id", "entente_id.name", "date")
    def _compute_name(self):
        for rec in self:
            ent = rec.entente_id.name or ""
            rec.name = "%s — %s" % (ent, rec.date or "")
