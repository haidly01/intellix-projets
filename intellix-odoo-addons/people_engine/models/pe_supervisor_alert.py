# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeSupervisorAlert(models.Model):
    _name = "pe.supervisor.alert"
    _description = "Alerte superviseur RH"
    _inherit = ["mail.thread"]
    _order = "create_date desc, niveau desc"

    name = fields.Char(string="Titre", required=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    superviseur_id = fields.Many2one(
        "hr.employee",
        string="Superviseur",
        default=lambda self: self.env.user.employee_id,
    )
    type_alerte = fields.Selection(
        [
            ("log_manquant_4h", "Log manquant 4h+"),
            ("log_manquant_24h", "Log manquant 24h+"),
            ("pause_depassee", "Pause dépassée"),
            ("pause_quota", "Quota pausettes"),
            ("absence", "Absence"),
            ("session_inactive", "Session inactive"),
            ("crm_note_manquante", "Note CRM manquante"),
            ("crm_saisie_retard", "Saisie CRM en retard"),
            ("crm_taux_bas", "Taux saisie CRM bas"),
            ("kpi_sous_seuil", "KPI sous seuil"),
            ("prescription_20j", "Prescription J-20"),
        ],
        required=True,
        index=True,
    )
    niveau = fields.Selection(
        [
            ("info", "Info"),
            ("warning", "Avertissement"),
            ("critique", "Critique"),
        ],
        default="warning",
        required=True,
    )
    message = fields.Text(required=True)
    lu = fields.Boolean(string="Lu", default=False)
    action_requise = fields.Boolean(string="Action requise", default=True)
    auto_generee = fields.Boolean(string="Auto-générée", default=True)
    incident_id = fields.Many2one("pe.disciplinary.incident", string="Incident lié")
    date_alerte = fields.Datetime(default=fields.Datetime.now)
    state = fields.Selection(
        [("active", "Active"), ("traitee", "Traitée"), ("ignoree", "Ignorée")],
        default="active",
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    def action_mark_read(self):
        self.write({"lu": True})

    def action_contact(self):
        self.ensure_one()
        employee = self.employee_id
        partner = employee.user_id.partner_id if employee.user_id else False
        if partner:
            return {
                "type": "ir.actions.act_window",
                "name": _("Contacter"),
                "res_model": "mail.compose.message",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_model": "hr.employee",
                    "default_res_ids": [employee.id],
                    "default_partner_ids": [partner.id],
                    "default_subject": self.name,
                    "default_body": self.message,
                },
            }
        return True

    def action_create_incident(self):
        self.ensure_one()
        type_map = {
            "log_manquant_4h": "log_manquant",
            "log_manquant_24h": "log_manquant",
            "pause_depassee": "pause_depassee",
            "pause_quota": "pause_quota",
            "absence": "absence",
            "session_inactive": "session_inactive",
            "crm_note_manquante": "crm_note_manquante",
            "crm_saisie_retard": "crm_note_manquante",
            "crm_taux_bas": "crm_note_manquante",
            "kpi_sous_seuil": "kpi_sous_seuil",
            "prescription_20j": "recidive",
        }
        gravite_map = {
            "info": "info",
            "warning": "modere",
            "critique": "grave",
        }
        incident = self.env["pe.disciplinary.incident"].create(
            {
                "employee_id": self.employee_id.id,
                "superviseur_id": self.superviseur_id.id or self.env.user.employee_id.id,
                "type_incident": type_map.get(self.type_alerte, "autre"),
                "gravite": gravite_map.get(self.niveau, "modere"),
                "description": self.message,
                "source": "alerte",
                "alert_id": self.id,
            }
        )
        self.write({"incident_id": incident.id, "state": "traitee", "lu": True})
        return {
            "type": "ir.actions.act_window",
            "name": _("Incident disciplinaire"),
            "res_model": "pe.disciplinary.incident",
            "res_id": incident.id,
            "view_mode": "form",
        }

    def action_ignore(self):
        self.write({"state": "ignoree", "lu": True, "action_requise": False})

    @api.model
    def cron_auto_detect(self):
        return self.env["pe.disciplinary.service"].sudo().run_auto_detection()
