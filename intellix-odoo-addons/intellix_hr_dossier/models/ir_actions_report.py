# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ReportIntellixHrAttestationMixin(models.AbstractModel):
    _name = "report.intellix_hr_dossier.attestation_mixin"
    _description = "Mixin données attestations RH"

    @api.model
    def _get_wizard(self, data):
        wizard_id = (data or {}).get("wizard_id")
        if wizard_id:
            return self.env["intellix_hr_dossier.attestation.wizard"].browse(
                wizard_id
            ).exists()
        return self.env["intellix_hr_dossier.attestation.wizard"]

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.employee"].browse(docids)
        wizard = self._get_wizard(data)
        company = docs[:1]._get_attestation_company() if docs else self.env.company
        partner = company.partner_id
        signatory = docs[:1]._get_attestation_signatory(wizard) if docs else {}
        doc_date = fields.Date.today()
        if wizard and wizard.document_date:
            doc_date = wizard.document_date
        elif data and data.get("document_date"):
            doc_date = fields.Date.from_string(data["document_date"])
        return {
            "doc_ids": docids,
            "doc_model": "hr.employee",
            "docs": docs,
            "data": data or {},
            "wizard": wizard,
            "company": company,
            "partner": partner,
            "signatory": signatory,
            "document_date": doc_date,
            "leave_reason": (data or {}).get("leave_reason")
            or (wizard.leave_reason if wizard else ""),
            "attestation_usage": (data or {}).get("attestation_usage")
            or (wizard.attestation_usage if wizard else ""),
            "establishment": (data or {}).get("establishment")
            or (wizard.establishment if wizard else ""),
            "internship": docs[:1]._get_active_internship(
                (data or {}).get("internship_id")
            )
            if docs
            else self.env["hr.internship"],
        }


class ReportAttestationTravail(models.AbstractModel):
    _name = "report.intellix_hr_dossier.report_attestation_travail"
    _inherit = "report.intellix_hr_dossier.attestation_mixin"
    _description = "Attestation de travail"


class ReportAttestationSalaire(models.AbstractModel):
    _name = "report.intellix_hr_dossier.report_attestation_salaire"
    _inherit = "report.intellix_hr_dossier.attestation_mixin"
    _description = "Attestation de salaire"


class ReportAttestationCnss(models.AbstractModel):
    _name = "report.intellix_hr_dossier.report_attestation_cnss"
    _inherit = "report.intellix_hr_dossier.attestation_mixin"
    _description = "Attestation CNSS"


class ReportCertificatTravail(models.AbstractModel):
    _name = "report.intellix_hr_dossier.report_certificat_travail"
    _inherit = "report.intellix_hr_dossier.attestation_mixin"
    _description = "Certificat de travail"


class ReportAttestationStage(models.AbstractModel):
    _name = "report.intellix_hr_dossier.report_attestation_stage"
    _inherit = "report.intellix_hr_dossier.attestation_mixin"
    _description = "Attestation de stage"
