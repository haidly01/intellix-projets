# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError


class CnssExportWizard(models.TransientModel):
    _name = "cnss.export.wizard"
    _description = "Export CNSS / Damancom (CSV mensuel)"

    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )
    month = fields.Selection(
        [
            ("1", "Janvier"),
            ("2", "Février"),
            ("3", "Mars"),
            ("4", "Avril"),
            ("5", "Mai"),
            ("6", "Juin"),
            ("7", "Juillet"),
            ("8", "Août"),
            ("9", "Septembre"),
            ("10", "Octobre"),
            ("11", "Novembre"),
            ("12", "Décembre"),
        ],
        string="Mois",
        required=True,
        default=lambda self: str(fields.Date.today().month),
    )
    year = fields.Integer(
        string="Année",
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    file_data = fields.Binary(string="Fichier", readonly=True)
    file_name = fields.Char(string="Nom fichier", readonly=True)

    def action_export(self):
        self.ensure_one()
        if not self.env["res.company"]._is_morocco_payroll_company(self.company_id):
            raise UserError(_("Cette société n'est pas configurée pour la paie Maroc."))

        month = int(self.month)
        from datetime import date
        import calendar

        period_start = date(self.year, month, 1)
        period_end = date(self.year, month, calendar.monthrange(self.year, month)[1])

        payslips = self.env["hr.payslip.ma"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("validated", "paid")),
                ("period_start", "<=", period_end),
                ("period_end", ">=", period_start),
            ]
        )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "N_CNSS",
            "NOM",
            "CIN",
            "BRUT",
            "BASE_CNSS",
            "CNSS_SALARIE",
            "CNSS_PATRON",
            "AMO_SALARIE",
            "AMO_PATRON",
            "PERIODE_DEBUT",
            "PERIODE_FIN",
        ])

        for slip in payslips:
            lines = {l.code: l for l in slip.line_ids}
            cnss_emp = lines.get("CNSS_EMP")
            cnss_pat = lines.get("CNSS_PAT")
            amo_emp = lines.get("AMO_EMP")
            amo_pat = lines.get("AMO_PAT")
            writer.writerow([
                slip.employee_id.x_cnss_number or "",
                slip.employee_id.name or "",
                slip.employee_id.x_cin_number or "",
                "%.2f" % slip.gross_salary,
                "%.2f" % (cnss_emp.base_amount if cnss_emp else 0.0),
                "%.2f" % (cnss_emp.amount if cnss_emp else 0.0),
                "%.2f" % (cnss_pat.employer_amount if cnss_pat else 0.0),
                "%.2f" % (amo_emp.amount if amo_emp else 0.0),
                "%.2f" % (amo_pat.employer_amount if amo_pat else 0.0),
                slip.period_start.strftime("%d/%m/%Y"),
                slip.period_end.strftime("%d/%m/%Y"),
            ])

        content = output.getvalue().encode("utf-8-sig")
        filename = "cnss_export_%s_%02d.csv" % (self.year, month)
        self.write(
            {
                "file_data": base64.b64encode(content),
                "file_name": filename,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_download(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%s&field=file_data&filename_field=file_name&download=true"
            % (self._name, self.id),
            "target": "self",
        }
