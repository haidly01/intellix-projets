# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeAbsenceDetected(models.Model):
    _name = "pe.absence.detected"
    _description = "Absence détectée"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_absence desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("pe.absence.detected")
        or "ABS",
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    date_absence = fields.Date(string="Date absence", required=True, index=True, tracking=True)
    heure_detection = fields.Datetime(string="Heure détection", default=fields.Datetime.now)
    statut = fields.Selection(
        [
            ("detectee", "Détectée"),
            ("justifiee", "Justifiée"),
            ("injustifiee", "Injustifiée"),
            ("conge_valide", "Congé valide"),
            ("erreur_systeme", "Erreur système"),
        ],
        default="detectee",
        required=True,
        tracking=True,
    )
    motif = fields.Char(string="Motif")
    justificatif_id = fields.Many2one("ir.attachment", string="Justificatif")
    incident_id = fields.Many2one("pe.disciplinary.incident", string="Incident lié", readonly=True)
    impact_paie = fields.Boolean(string="Impact paie", default=False)
    heures_deduites = fields.Float(string="Heures déduites", default=8.0)
    source_detection = fields.Selection(
        [
            ("cron_matin", "Cron matin (10h)"),
            ("cron_soir", "Cron soir (18h)"),
            ("superviseur", "Superviseur"),
        ],
        default="cron_matin",
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _employee_date_unique = models.Constraint(
        "unique(employee_id, date_absence)",
        "Une détection par employé et par jour.",
    )

    def action_mark_justifiee(self):
        for rec in self:
            if rec.statut not in ("detectee", "injustifiee"):
                raise UserError(_("Seules les absences détectées peuvent être justifiées."))
            rec.write({"statut": "justifiee", "impact_paie": False})

    def action_mark_injustifiee(self):
        svc = self.env["pe.absence.detection.service"].sudo()
        for rec in self:
            if rec.statut not in ("detectee", "justifiee"):
                raise UserError(_("Statut incompatible avec classification injustifiée."))
            svc.classifier_injustifiee(rec)

    def action_mark_erreur(self):
        self.write({"statut": "erreur_systeme", "impact_paie": False})

    @api.model
    def cron_detection_matin(self):
        return self.env["pe.absence.detection.service"].sudo().detection_matin()

    @api.model
    def cron_detection_soir(self):
        return self.env["pe.absence.detection.service"].sudo().detection_soir()
