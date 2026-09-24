# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AttestationWizard(models.TransientModel):
    _name = "intellix_hr_dossier.attestation.wizard"
    _description = "Assistant attestations RH"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employé",
        required=True,
    )
    company_id = fields.Many2one(
        related="employee_id.company_id",
        readonly=True,
    )
    report_type = fields.Selection(
        selection=[
            ("work", "Attestation de travail"),
            ("salary", "Attestation de salaire"),
            ("cnss", "Attestation d'affiliation CNSS"),
            ("termination", "Certificat de travail (fin de contrat)"),
            ("internship", "Attestation de stage"),
        ],
        string="Type de document",
        required=True,
        default="work",
    )
    leave_reason = fields.Text(
        string="Motif de départ",
        help="Motif figurant sur le certificat de travail.",
    )
    attestation_usage = fields.Char(
        string="Usage de l'attestation",
        help="Destinataire ou objet (ex. banque, consulat…).",
    )
    establishment = fields.Char(
        string="Établissement (stage)",
        help="École ou organisme pour l'attestation de stage.",
    )
    internship_id = fields.Many2one(
        "hr.internship",
        string="Stage",
        domain="[('employee_id', '=', employee_id)]",
    )
    signatory_name = fields.Char(string="Nom du signataire")
    signatory_title = fields.Char(string="Fonction du signataire")
    city = fields.Char(string="Fait à (ville)")
    document_date = fields.Date(
        string="Date du document",
        default=fields.Date.context_today,
    )

    def _report_action(self, xmlid):
        self.ensure_one()
        report = self.env.ref(xmlid)
        return report.report_action(
            self.employee_id,
            data={
                "wizard_id": self.id,
                "leave_reason": self.leave_reason,
                "attestation_usage": self.attestation_usage,
                "establishment": self.establishment
                or (self.internship_id.establishment if self.internship_id else ""),
                "signatory_name": self.signatory_name,
                "signatory_title": self.signatory_title,
                "city": self.city,
                "document_date": self.document_date.isoformat()
                if self.document_date
                else False,
                "internship_id": self.internship_id.id if self.internship_id else False,
            },
        )

    def action_print(self):
        self.ensure_one()
        mapping = {
            "work": "intellix_hr_dossier.action_report_attestation_travail",
            "salary": "intellix_hr_dossier.action_report_attestation_salaire",
            "cnss": "intellix_hr_dossier.action_report_attestation_cnss",
            "termination": "intellix_hr_dossier.action_report_certificat_travail",
            "internship": "intellix_hr_dossier.action_report_attestation_stage",
        }
        xmlid = mapping.get(self.report_type)
        if not xmlid:
            return False
        if self.report_type == "termination" and not self.leave_reason:
            return self._report_action(xmlid)
        return self._report_action(xmlid)
