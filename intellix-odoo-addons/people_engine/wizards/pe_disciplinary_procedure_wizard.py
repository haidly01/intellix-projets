# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeDisciplinaryProcedureWizard(models.TransientModel):
    _name = "pe.disciplinary.procedure.wizard"
    _description = "Créer procédure depuis incident"

    incident_id = fields.Many2one("pe.disciplinary.incident", required=True)
    employee_id = fields.Many2one("hr.employee", required=True)
    type_sanction = fields.Selection(
        selection="_selection_type_sanction",
        string="Type de sanction",
        required=True,
    )
    description_faits = fields.Text(string="Faits reprochés", required=True)
    impact_paie = fields.Boolean(string="Impact paie")
    jours_mise_a_pied = fields.Integer(string="Jours mise à pied")
    heures_deduction = fields.Float(string="Heures déduction")
    generate_convocation = fields.Boolean(
        string="Générer convocation immédiatement",
        default=True,
    )

    @api.model
    def _selection_type_sanction(self):
        return self.env["pe.disciplinary.procedure"]._fields["type_sanction"].selection

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        incident = self.env["pe.disciplinary.incident"].browse(
            self.env.context.get("default_incident_id")
        )
        if incident:
            res.setdefault("description_faits", incident.description)
            res.setdefault("impact_paie", incident.impact_paie)
            res.setdefault("heures_deduction", incident.heures_concernees)
            if incident.jours_mise_a_pied_suggere:
                res.setdefault("jours_mise_a_pied", incident.jours_mise_a_pied_suggere)
        return res

    def action_create_procedure(self):
        self.ensure_one()
        self.env["pe.disciplinary.service"].sudo().enforce_human_validation(
            self.type_sanction, "créer la procédure"
        )
        procedure = self.env["pe.disciplinary.procedure"].create(
            {
                "employee_id": self.employee_id.id,
                "incident_id": self.incident_id.id,
                "superviseur_id": self.incident_id.superviseur_id.id
                or self.env.user.employee_id.id,
                "type_sanction": self.type_sanction,
                "description_faits": self.description_faits,
                "impact_paie": self.impact_paie,
                "jours_mise_a_pied": self.jours_mise_a_pied,
                "heures_deduction": self.heures_deduction,
            }
        )
        if self.generate_convocation and self.type_sanction in (
            "licenciement_faute_grave",
            "licenciement_insuffisance",
            "mise_en_demeure",
        ):
            self.env["pe.disciplinary.service"].sudo().generate_letter(procedure, "convocation")
        elif self.type_sanction == "avertissement_ecrit":
            self.env["pe.disciplinary.service"].sudo().generate_letter(
                procedure, "avertissement_ecrit"
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Procédure disciplinaire",
            "res_model": "pe.disciplinary.procedure",
            "res_id": procedure.id,
            "view_mode": "form",
        }
