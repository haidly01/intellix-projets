# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayslipLineMa(models.Model):
    _name = "hr.payslip.line.ma"
    _description = "Ligne bulletin de paie Maroc"
    _order = "sequence, id"

    payslip_id = fields.Many2one(
        "hr.payslip.ma",
        string="Bulletin",
        required=True,
        ondelete="cascade",
        index=True,
    )
    rule_id = fields.Many2one("hr.salary.rule.ma", string="Règle")
    sequence = fields.Integer(default=10)
    code = fields.Char(string="Code")
    name = fields.Char(string="Libellé", required=True)
    category = fields.Selection(
        [
            ("gain", "Gain"),
            ("retenue_salariale", "Retenue salariale"),
            ("charge_patronale", "Charge patronale"),
            ("info", "Information"),
        ],
        string="Catégorie",
        required=True,
    )
    amount = fields.Float(string="Montant salarié", digits=(16, 2))
    employer_amount = fields.Float(string="Montant employeur", digits=(16, 2))
    base_amount = fields.Float(string="Base", digits=(16, 2))
    rate = fields.Float(string="Taux (%)")
    appears_on_payslip = fields.Boolean(default=True)
