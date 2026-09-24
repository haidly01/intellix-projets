# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeKpiSnapshot(models.Model):
    _name = "pe.kpi.snapshot"
    _description = "Snapshot KPI hebdomadaire"
    _inherit = ["mail.thread"]
    _order = "annee desc, semaine desc, employee_id"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        compute="_compute_name",
        store=True,
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    departement = fields.Selection(
        [
            ("commercial", "Commercial"),
            ("marketing", "Marketing"),
            ("call_center", "Call center"),
        ],
        required=True,
        index=True,
    )
    semaine = fields.Integer(string="Semaine ISO", required=True, index=True)
    annee = fields.Integer(required=True, index=True)
    date_calcul = fields.Datetime(default=fields.Datetime.now)
    periode_debut = fields.Date(string="Début (lundi)", required=True)
    periode_fin = fields.Date(string="Fin (vendredi)", required=True)

    # KPI commercial
    leads_crees = fields.Integer(string="Leads créés")
    leads_qualifies = fields.Integer(string="Leads qualifiés")
    opportunites = fields.Integer(string="Opportunités")
    deals_gagnes = fields.Integer(string="Deals gagnés")
    ca_genere = fields.Float(string="CA généré (MAD)")
    taux_conversion_pc = fields.Float(string="Taux conversion %")
    rdv_pris = fields.Integer(string="RDV pris")
    relances_effectuees = fields.Integer(string="Relances")
    pipeline_valeur = fields.Float(string="Pipeline (MAD)")

    # KPI marketing
    taches_assignees = fields.Integer(string="Tâches assignées")
    taches_completees = fields.Integer(string="Tâches complétées")
    taux_completion_pc = fields.Float(string="Taux complétion %")
    publications_faites = fields.Integer(string="Publications")
    leads_generes_marketing = fields.Integer(string="Leads marketing")
    heures_loguees = fields.Float(string="Heures loguées")
    campagnes_actives = fields.Integer(string="Campagnes actives")

    statut_global = fields.Selection(
        [
            ("ok", "OK"),
            ("attention", "Attention"),
            ("critique", "Critique"),
        ],
        default="ok",
        required=True,
        tracking=True,
    )
    alerte_envoyee = fields.Boolean(string="Alerte envoyée", default=False)
    incident_cree = fields.Boolean(string="Incident créé", default=False)
    incident_id = fields.Many2one("pe.disciplinary.incident", string="Incident lié", readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _employee_week_unique = models.Constraint(
        "unique(employee_id, annee, semaine, departement)",
        "Un snapshot par employé, semaine et département.",
    )

    @api.depends("employee_id", "semaine", "annee", "departement")
    def _compute_name(self):
        for rec in self:
            emp = rec.employee_id.name or "?"
            rec.name = "KPI S%s/%s — %s (%s)" % (
                rec.semaine or 0,
                rec.annee or 0,
                emp,
                rec.departement or "",
            )

    @api.model
    def cron_kpi_hebdomadaire(self):
        return self.env["pe.kpi.snapshot.service"].sudo().cron_kpi_hebdomadaire()
