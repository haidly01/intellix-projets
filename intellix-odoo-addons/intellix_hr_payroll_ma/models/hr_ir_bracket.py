# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrIrBracket(models.Model):
    _name = "hr.ir.bracket"
    _description = "Tranche IR Maroc (annuelle)"
    _order = "sequence, min_amount"

    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )
    sequence = fields.Integer(default=10)
    min_amount = fields.Float(string="Montant min (MAD/an)", required=True)
    max_amount = fields.Float(
        string="Montant max (MAD/an)",
        help="0 = illimité",
    )
    rate = fields.Float(string="Taux (%)", required=True)
    active = fields.Boolean(default=True)

    @api.depends("min_amount", "max_amount", "rate")
    def _compute_name(self):
        for rec in self:
            if rec.max_amount:
                rec.name = "%s — %s MAD : %.2f%%" % (
                    rec.min_amount,
                    rec.max_amount,
                    rec.rate,
                )
            else:
                rec.name = "> %s MAD : %.2f%%" % (rec.min_amount, rec.rate)
