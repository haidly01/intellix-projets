# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayrollStructureMa(models.Model):
    _name = "hr.payroll.structure.ma"
    _description = "Structure de paie Maroc"
    _order = "name"

    name = fields.Char(string="Nom", required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )
    rule_ids = fields.Many2many(
        "hr.salary.rule.ma",
        "hr_payroll_structure_ma_rule_rel",
        "structure_id",
        "rule_id",
        string="Règles salariales",
        domain="[('company_id', '=', company_id)]",
    )
    note = fields.Text(string="Description")
