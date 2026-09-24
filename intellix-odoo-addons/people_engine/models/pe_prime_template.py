# -*- coding: utf-8 -*-
from odoo import fields, models


class PePrimeTemplate(models.Model):
    _name = "pe.prime.template"
    _description = "Modèle de prime variable"
    _order = "name"

    name = fields.Char(required=True, string="Nom du modèle")
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    calculation_type = fields.Selection(
        [
            (
                "percent_extra_revenue",
                "% sur revenus extra (après objectif)",
            ),
            ("percent_revenue", "% sur revenus générés"),
            ("fixed_on_objective", "Prime fixe à l'objectif"),
            ("fixed_target", "Montant variable cible"),
        ],
        string="Type de calcul",
        required=True,
        default="percent_extra_revenue",
    )
    objective_period = fields.Selection(
        [
            ("weekly", "Hebdomadaire"),
            ("monthly", "Mensuel"),
            ("quarterly", "Trimestriel"),
        ],
        string="Période objectif",
        default="monthly",
        help="Période de l'objectif KPI lié à cette prime variable.",
    )
    montant_variable = fields.Float(
        string="Part variable (cible)",
        help="Montant variable cible ou prime fixe selon le type de calcul.",
    )
    taux_commission = fields.Float(
        string="Taux variable (%)",
        help="Pourcentage appliqué sur les revenus ou la part extra.",
    )
    description_variable = fields.Text(
        string="Description du variable",
        help="Règles affichées sur le profil et le contrat (critères, plafond, paliers…).",
    )
    challenges_eligible = fields.Boolean(
        string="Éligible challenges (défaut)",
        default=True,
        help="Suggestion pour les contrats utilisant ce modèle.",
    )
    prime_performance_base = fields.Float(
        string="Prime performance KPI (défaut)",
        help="Montant suggéré pour la prime conditionnelle KPI (MAD).",
    )
