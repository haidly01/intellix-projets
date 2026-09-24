# -*- coding: utf-8 -*-
{
    "name": "IntelliX — Paie Maroc",
    "version": "19.0.1.1.0",
    "category": "Human Resources/Payroll",
    "summary": "Bulletins de paie Maroc (CNSS, AMO, CIMR, IR) — Digital Doorway",
    "description": """
        Paie Maroc pour IntelliX RH : bulletins, cotisations sociales, IR,
        comptabilisation CGNC, exports CNSS/Damancom et état 9421.

        La paie Canada (Agence Doorway Inc.) est gérée par un module séparé
        (intellix_hr_payroll_ca — à venir).
    """,
    "author": "Agence Doorway Inc.",
    "depends": [
        "hr",
        "account",
        "intellix_hr_dossier",
        "people_engine",
    ],
    "data": [
        "security/hr_payroll_ma_security.xml",
        "security/ir.model.access.csv",
        "data/payroll_ma_access_sync.xml",
        "data/ir_sequence_data.xml",
        "data/hr_ir_config_data.xml",
        "data/hr_ir_bracket_data.xml",
        "data/hr_salary_rule_data.xml",
        "data/account_payroll_ma_data.xml",
        "views/res_company_views.xml",
        "views/hr_ir_views.xml",
        "views/hr_salary_rule_ma_views.xml",
        "views/hr_payroll_structure_ma_views.xml",
        "views/hr_payslip_ma_views.xml",
        "wizards/cnss_export_wizard_views.xml",
        "wizards/ir9421_export_wizard_views.xml",
        "wizards/generate_payslip_wizard_views.xml",
        "views/pe_employment_contract_views.xml",
        "reports/payslip_report.xml",
        "reports/payslip_template.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
