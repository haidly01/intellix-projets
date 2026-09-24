# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeAgentAssignment(models.Model):
    _name = "pe.agent.assignment"
    _description = "Attribution lead agent IA → employé"
    _order = "date_attribution desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    agent_ia_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA source",
        required=True,
    )
    lead_id = fields.Many2one("crm.lead", string="Lead CRM")
    date_attribution = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    score_ia = fields.Float(string="Score qualification IA (/100)")
    tags_ia = fields.Char(string="Tags détectés par IA")
    projet_principal = fields.Char(string="Projet principal détecté")
    projets_detectes = fields.Char(
        string="Projets détectés (JSON)",
        help='Ex: ["thermopompe","isolation","toiture"]',
    )
    statut = fields.Selection(
        [
            ("attribue", "Attribué"),
            ("contacte", "Contacté"),
            ("qualifie", "Qualifié confirmé"),
            ("converti", "Converti (RDV / vente)"),
            ("perdu", "Perdu"),
            ("invalide", "Lead invalide"),
        ],
        default="attribue",
        tracking=True,
    )
    date_premier_contact = fields.Datetime()
    date_qualification = fields.Datetime()
    notes_employe = fields.Text()
    upsell_log_ids = fields.One2many(
        "pe.prime.upsell.log", "assignment_id", string="Leads upsell détectés"
    )
    nb_upsells = fields.Integer(compute="_compute_upsells", store=True)
    prime_upsell_generee = fields.Float(compute="_compute_upsells", store=True)

    @api.depends("upsell_log_ids", "upsell_log_ids.prime_generee")
    def _compute_upsells(self):
        for rec in self:
            rec.nb_upsells = len(rec.upsell_log_ids)
            rec.prime_upsell_generee = sum(rec.upsell_log_ids.mapped("prime_generee"))

    def action_declarer_upsell(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Déclarer upsell",
            "res_model": "pe.prime.upsell.log",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_assignment_id": self.id,
                "default_employee_id": self.employee_id.id,
                "default_projet_original": self.projet_principal,
            },
        }


class PePrimeUpsellLog(models.Model):
    _name = "pe.prime.upsell.log"
    _description = "Lead upsell détecté par employé"
    _order = "date desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    assignment_id = fields.Many2one(
        "pe.agent.assignment", required=True, ondelete="cascade"
    )
    lead_id = fields.Many2one("crm.lead")
    date = fields.Date(default=fields.Date.context_today, required=True)
    projet_original = fields.Char(string="Projet original (IA)")
    projet_upsell = fields.Char(
        string="Projet supplémentaire détecté", required=True
    )
    prime_generee = fields.Float(string="Prime générée")
    devise = fields.Char(default="EUR")
    valide_par_manager = fields.Boolean(
        string="Validé par manager",
        help="Human-in-the-loop : le manager valide le lead upsell.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._apply_prime_amount()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "valide_par_manager" in vals and vals["valide_par_manager"]:
            for rec in self:
                rec._apply_prime_amount()
        return res

    def _apply_prime_amount(self):
        for rec in self:
            dept = self.env["pe.department"].search(
                [("employee_ids", "in", [rec.employee_id.id])], limit=1
            )
            montant = 5.0
            if dept:
                config = dept.prime_config_ids.filtered(
                    lambda c: c.type_prime == "upsell_lead" and c.actif
                )[:1]
                if config:
                    montant = config.montant_par_unite
            if rec.valide_par_manager:
                rec.prime_generee = montant
