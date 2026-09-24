# -*- coding: utf-8 -*-
from odoo import fields, models


class HrSalaryRuleMa(models.Model):
    _name = "hr.salary.rule.ma"
    _description = "Règle salariale Maroc"
    _order = "sequence, code"

    name = fields.Char(string="Libellé", required=True, translate=True)
    code = fields.Char(string="Code", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )
    category = fields.Selection(
        [
            ("gain", "Gain"),
            ("retenue_salariale", "Retenue salariale"),
            ("charge_patronale", "Charge patronale"),
            ("info", "Information"),
        ],
        string="Catégorie",
        required=True,
        default="retenue_salariale",
    )
    computation_type = fields.Selection(
        [
            ("fixed", "Montant fixe"),
            ("percentage", "Pourcentage"),
            ("ir_ma", "Impôt sur le revenu (IR)"),
        ],
        string="Type de calcul",
        required=True,
        default="percentage",
    )
    base_type = fields.Selection(
        [
            ("gross", "Salaire brut"),
            ("cnss_capped", "Base CNSS plafonnée"),
            ("gross_if_cimr", "Brut si CIMR actif"),
        ],
        string="Base de calcul",
        default="gross",
    )
    rate = fields.Float(
        string="Taux (%)",
        help="Taux indicatif — à mettre à jour via configuration annuelle.",
    )
    employer_rate = fields.Float(
        string="Taux employeur (%)",
        help="Pour les charges patronales à double taux (ex. CNSS).",
    )
    ceiling = fields.Float(
        string="Plafond",
        help="Plafond mensuel (ex. 6000 MAD pour CNSS). 0 = sans plafond.",
    )
    fixed_amount = fields.Float(string="Montant fixe")
    sequence = fields.Integer(default=10)
    appears_on_payslip = fields.Boolean(string="Afficher sur bulletin", default=True)
    account_debit_id = fields.Many2one(
        "account.account",
        string="Compte débit",
        domain="[('company_ids', 'in', company_id)]",
    )
    account_credit_id = fields.Many2one(
        "account.account",
        string="Compte crédit",
        domain="[('company_ids', 'in', company_id)]",
    )
    note = fields.Text(string="Note")

    _code_company_unique = models.Constraint(
        "unique(code, company_id)",
        "Le code de règle doit être unique par société.",
    )
