# -*- coding: utf-8 -*-
import datetime

from odoo import _, api, fields, models


class PeDisciplinaryIncident(models.Model):
    _name = "pe.disciplinary.incident"
    _description = "Incident disciplinaire"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_incident desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("pe.disciplinary.incident")
        or "INC",
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    superviseur_id = fields.Many2one(
        "hr.employee",
        string="Superviseur",
        default=lambda self: self.env.user.employee_id.parent_id,
        tracking=True,
    )
    profile_id = fields.Many2one(
        "pe.employee.profile",
        compute="_compute_profile_id",
        store=True,
    )
    date_incident = fields.Datetime(
        string="Date incident",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    date_detection = fields.Datetime(
        string="Date détection",
        default=fields.Datetime.now,
    )
    type_incident = fields.Selection(
        [
            ("log_manquant", "Log manquant"),
            ("pause_depassee", "Pause dépassée"),
            ("pause_quota", "Quota pausettes dépassé"),
            ("absence", "Absence non justifiée"),
            ("session_inactive", "Session inactive"),
            ("crm_note_manquante", "Note CRM manquante"),
            ("kpi_sous_seuil", "KPI sous seuil"),
            ("retard", "Retard répété"),
            ("comportement", "Comportement inapproprié"),
            ("refus_instruction", "Refus d'instruction"),
            ("fraude_log", "Fraude / manipulation logs"),
            ("confidentialite", "Violation confidentialité"),
            ("concurrence", "Concurrence déloyale"),
            ("non_conformite", "Non-conformité procédure"),
            ("recidive", "Récidive"),
            ("autre", "Autre"),
        ],
        required=True,
        tracking=True,
    )
    gravite = fields.Selection(
        [
            ("info", "Information"),
            ("mineur", "Mineur"),
            ("modere", "Modéré"),
            ("grave", "Grave"),
            ("critique", "Critique"),
        ],
        default="modere",
        required=True,
        tracking=True,
    )
    description = fields.Text(required=True)
    preuves = fields.Text(string="Preuves / éléments")
    source = fields.Selection(
        [
            ("manuel", "Manuel"),
            ("cron", "Détection automatique"),
            ("alerte", "Alerte superviseur"),
            ("crm", "CRM"),
            ("paie", "Paie"),
        ],
        default="manuel",
    )
    statut = fields.Selection(
        [
            ("nouveau", "Nouveau"),
            ("en_cours", "En cours"),
            ("procedure", "Procédure engagée"),
            ("clos", "Clos"),
            ("prescrit", "Prescrit"),
            ("ignore", "Ignoré"),
        ],
        default="nouveau",
        tracking=True,
    )
    procedure_id = fields.Many2one(
        "pe.disciplinary.procedure",
        string="Procédure",
        readonly=True,
    )
    alert_id = fields.Many2one("pe.supervisor.alert", string="Alerte source", readonly=True)
    impact_paie = fields.Boolean(string="Impact paie", default=False)
    heures_concernees = fields.Float(string="Heures concernées")
    jours_prescription = fields.Integer(
        string="Jours avant prescription",
        compute="_compute_prescription",
        store=True,
    )
    sanction_suggeree = fields.Selection(
        selection="_selection_type_sanction",
        string="Sanction suggérée",
        compute="_compute_sanction_suggeree",
        store=True,
    )
    sanction_code_matrice = fields.Char(
        string="Code matrice",
        compute="_compute_sanction_suggeree",
        store=True,
    )
    jours_mise_a_pied_suggere = fields.Integer(
        string="Jours MAP suggérés",
        compute="_compute_sanction_suggeree",
        store=True,
    )
    coaching_requis = fields.Boolean(
        string="Coaching requis",
        compute="_compute_sanction_suggeree",
        store=True,
    )
    validation_humaine_requise = fields.Boolean(
        string="Validation RH requise",
        compute="_compute_sanction_suggeree",
        store=True,
    )
    incident_count_30d = fields.Integer(
        string="Incidents 30 j (même type)",
        compute="_compute_sanction_suggeree",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
    )

    @api.model
    def _selection_type_sanction(self):
        return self.env["pe.disciplinary.procedure"]._fields["type_sanction"].selection

    @api.depends("employee_id")
    def _compute_profile_id(self):
        Profile = self.env["pe.employee.profile"].sudo()
        for rec in self:
            rec.profile_id = Profile.search(
                [("employee_id", "=", rec.employee_id.id)], limit=1
            ).id

    @api.depends("date_incident", "statut")
    def _compute_prescription(self):
        from odoo.addons.people_engine.services.disciplinary_config import get_prescription_days

        prescription_days = get_prescription_days(self.env)
        today = fields.Date.today()
        for rec in self:
            if not rec.date_incident or rec.statut in ("clos", "prescrit", "ignore"):
                rec.jours_prescription = 0
                continue
            incident_date = rec.date_incident.date() if isinstance(
                rec.date_incident, datetime.datetime
            ) else rec.date_incident
            days = (today - incident_date).days
            rec.jours_prescription = max(prescription_days - days, 0)

    @api.depends("employee_id", "type_incident")
    def _compute_sanction_suggeree(self):
        svc = self.env["pe.disciplinary.service"].sudo()
        for rec in self:
            if not rec.employee_id or not rec.type_incident:
                rec.sanction_suggeree = False
                rec.sanction_code_matrice = False
                rec.jours_mise_a_pied_suggere = 0
                rec.coaching_requis = False
                rec.validation_humaine_requise = False
                rec.incident_count_30d = 0
                continue
            count = svc.count_incidents_30d(rec.employee_id.id, rec.type_incident)
            rec.incident_count_30d = count
            detail = svc.suggerer_sanction_detail(rec.type_incident, count)
            rec.sanction_suggeree = detail.get("sanction_odoo")
            rec.sanction_code_matrice = detail.get("code_matrice")
            rec.jours_mise_a_pied_suggere = detail.get("jours_mise_a_pied", 0)
            rec.coaching_requis = detail.get("coaching_requis", False)
            rec.validation_humaine_requise = detail.get("validation_humaine_requise", False)

    def action_create_procedure(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Créer procédure disciplinaire"),
            "res_model": "pe.disciplinary.procedure.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_incident_id": self.id,
                "default_employee_id": self.employee_id.id,
                "default_type_sanction": self.sanction_suggeree,
            },
        }

    def action_close(self):
        self.write({"statut": "clos"})

    def action_ignore(self):
        self.write({"statut": "ignore"})

    @api.model
    def cron_check_prescription(self):
        """Marque les incidents > prescription_jours sans procédure comme prescrits."""
        from odoo.addons.people_engine.services.disciplinary_config import get_prescription_days

        limit = fields.Datetime.now() - datetime.timedelta(days=get_prescription_days(self.env))
        incidents = self.sudo().search(
            [
                ("date_incident", "<", limit),
                ("statut", "in", ("nouveau", "en_cours")),
                ("procedure_id", "=", False),
            ]
        )
        incidents.write({"statut": "prescrit"})
        return True
