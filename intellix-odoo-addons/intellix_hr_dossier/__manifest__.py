# -*- coding: utf-8 -*-
{
    "name": "IntelliX — Dossier RH Administratif",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "Dossier administratif Maroc (CIN, CNSS, médical) et attestations PDF",
    "description": """
        Dossier administratif employé (Maroc) : identité, résidence, CNSS,
        données médicales restreintes, alertes expiration CIN, attestations PDF.
    """,
    "author": "Agence Doorway Inc.",
    "depends": ["hr", "mail"],
    "data": [
        "security/hr_dossier_security.xml",
        "security/ir.model.access.csv",
        "data/cin_expiry_cron.xml",
        "views/res_company_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_internship_views.xml",
        "wizards/attestation_wizard_views.xml",
        "reports/attestation_templates.xml",
        "reports/attestation_reports.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
