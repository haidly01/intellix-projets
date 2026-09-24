# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrIrConfig(models.Model):
    _name = "hr.ir.config"
    _description = "Configuration IR Maroc"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )
    professional_expense_rate = fields.Float(
        string="Frais professionnels (%)",
        default=20.0,
        help="Pourcentage déductible du revenu brut annuel (indicatif).",
    )
    professional_expense_annual_cap = fields.Float(
        string="Plafond frais pro (MAD/an)",
        default=30000.0,
    )
    family_deduction_annual = fields.Float(
        string="Déduction familiale (MAD/personne/an)",
        default=360.0,
    )
    max_dependents = fields.Integer(
        string="Nombre max de personnes à charge",
        default=6,
    )
    include_spouse = fields.Boolean(
        string="Inclure conjoint(e)",
        default=True,
        help="Ajoute 1 personne à charge si situation familiale = marié(e).",
    )
    active = fields.Boolean(default=True)
    note = fields.Text(
        string="Note",
        default="Taux indicatifs — mettre à jour chaque année fiscale.",
    )

    _company_unique = models.Constraint(
        "unique(company_id)",
        "Une seule configuration IR par société.",
    )
