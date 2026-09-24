# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PePrimeTransaction(models.Model):
    """Journal des primes variables temps réel (Phase 4)."""

    _name = "pe.prime.transaction"
    _description = "Transaction prime variable"
    _order = "date desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    profile_id = fields.Many2one(
        "pe.employee.profile",
        compute="_compute_profile",
        store=True,
    )
    department_id = fields.Many2one("pe.department")
    prime_config_id = fields.Many2one("pe.prime.config", ondelete="set null")
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    type_prime = fields.Selection(
        [
            ("leads_confirmes", "Leads confirmés"),
            ("plateau_leads", "Plateau leads"),
            ("upsell_lead", "Upsell"),
            ("conversion_ia", "Conversion IA"),
            ("presence", "Présence"),
            ("coaching_valide", "Coaching validé"),
            ("deduction_absence", "Déduction absence"),
        ],
        required=True,
    )
    nb_leads = fields.Integer(string="Nb leads")
    montant = fields.Float(required=True)
    devise = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("CAD", "CAD")],
        default="MAD",
    )
    detail = fields.Char(string="Détail")
    mois = fields.Char(string="Mois", index=True)

    @api.depends("employee_id")
    def _compute_profile(self):
        Profile = self.env["pe.employee.profile"]
        for rec in self:
            rec.profile_id = (
                Profile.search([("employee_id", "=", rec.employee_id.id)], limit=1).id
                if rec.employee_id
                else False
            )
