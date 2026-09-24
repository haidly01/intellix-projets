# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeDepartment(models.Model):
    _name = "pe.department"
    _description = "Département People Engine"
    _rec_name = "name"
    _order = "name"

    name = fields.Char(string="Nom du département", required=True)
    code = fields.Char(string="Code", required=True)
    is_template = fields.Boolean(
        string="Département modèle",
        help="Si coché, peut être dupliqué pour créer d'autres départements.",
    )
    parent_template_id = fields.Many2one(
        "pe.department",
        string="Basé sur le modèle",
        domain=[("is_template", "=", True)],
    )
    employee_ids = fields.Many2many("hr.employee", string="Employés")
    manager_id = fields.Many2one("hr.employee", string="Responsable")
    nb_employees = fields.Integer(compute="_compute_nb_employees", store=True)
    work_type = fields.Selection(
        [
            ("prospection_froide", "Prospection froide (réseaux sociaux / VICIdial)"),
            ("qualification", "Qualification de leads entrants"),
            ("closing", "Closing / conversion"),
            ("support", "Support client"),
            ("mixte", "Mixte"),
        ],
        required=True,
        default="prospection_froide",
    )
    agent_ia_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA prospecteur",
        help="Agent IA qui travaille en parallèle des agents humains du département.",
    )
    objective_ids = fields.One2many(
        "pe.department.objective", "department_id", string="Objectifs"
    )
    prime_config_ids = fields.One2many(
        "pe.prime.config", "department_id", string="Configuration primes"
    )
    seuil_chute_pct = fields.Float(
        string="Tolérance chute leads (%)",
        default=25.0,
    )
    seuil_conversion_ia = fields.Float(
        string="Taux conversion leads IA minimum (%)",
        default=70.0,
    )
    pays_affectation = fields.Selection(
        [
            ("MA", "Maroc"),
            ("CA", "Canada"),
            ("FR", "France"),
            ("QC", "Québec"),
        ],
        string="Pays / site",
    )
    leads_qualifies_mois = fields.Integer(compute="_compute_stats_mois")
    taux_conversion_mois = fields.Float(compute="_compute_stats_mois")
    prime_totale_mois = fields.Float(compute="_compute_stats_mois")

    _code_unique = models.Constraint("unique(code)", "Le code département doit être unique.")

    @api.depends("employee_ids")
    def _compute_nb_employees(self):
        for rec in self:
            rec.nb_employees = len(rec.employee_ids)

    def _compute_stats_mois(self):
        import datetime

        today = datetime.date.today()
        debut = today.replace(day=1)
        PrimeLine = self.env["pe.prime.transaction"]
        Assignment = self.env["pe.agent.assignment"]
        for rec in self:
            emp_ids = rec.employee_ids.ids
            lines = PrimeLine.search(
                [
                    ("employee_id", "in", emp_ids),
                    ("date", ">=", debut),
                    ("type_prime", "=", "leads_confirmes"),
                ]
            )
            rec.leads_qualifies_mois = sum(lines.mapped("nb_leads"))
            rec.prime_totale_mois = sum(
                PrimeLine.search(
                    [("employee_id", "in", emp_ids), ("date", ">=", debut)]
                ).mapped("montant")
            )
            assignments = Assignment.search(
                [
                    ("employee_id", "in", emp_ids),
                    ("date_attribution", ">=", debut),
                ]
            )
            if assignments:
                conv = len(assignments.filtered(lambda r: r.statut == "converti"))
                rec.taux_conversion_mois = conv / len(assignments) * 100
            else:
                rec.taux_conversion_mois = 0.0

    def action_dupliquer_comme_departement(self):
        self.ensure_one()
        new_dept = self.copy(
            {
                "name": _("%s (copie)") % self.name,
                "code": "%s-COPY" % self.code,
                "is_template": False,
                "parent_template_id": self.id,
                "employee_ids": [(5,)],
            }
        )
        for obj in self.objective_ids:
            obj.copy({"department_id": new_dept.id})
        for prime in self.prime_config_ids:
            prime.copy({"department_id": new_dept.id})
        return {
            "type": "ir.actions.act_window",
            "name": new_dept.name,
            "res_model": "pe.department",
            "res_id": new_dept.id,
            "view_mode": "form",
            "target": "current",
        }
