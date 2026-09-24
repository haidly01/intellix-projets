# -*- coding: utf-8 -*-
from odoo import fields, models


class PePayrollBulletinDeductionLine(models.Model):
    _name = "pe.payroll.bulletin.deduction.line"
    _description = "Ligne déduction disciplinaire bulletin"
    _order = "id"

    bulletin_id = fields.Many2one(
        "pe.payroll.bulletin",
        required=True,
        ondelete="cascade",
        index=True,
    )
    procedure_id = fields.Many2one("pe.disciplinary.procedure", string="Procédure")
    incident_id = fields.Many2one("pe.disciplinary.incident", string="Incident")
    label = fields.Char(required=True)
    type_deduction = fields.Selection(
        [
            ("mise_a_pied", "Mise à pied"),
            ("log_manquant", "Heures non reconnues"),
            ("licenciement", "Licenciement faute grave"),
            ("autre", "Autre"),
        ],
        default="autre",
    )
    heures = fields.Float(string="Heures")
    jours = fields.Float(string="Jours")
    montant = fields.Float(string="Montant", required=True)
    devise = fields.Char(default="MAD")
