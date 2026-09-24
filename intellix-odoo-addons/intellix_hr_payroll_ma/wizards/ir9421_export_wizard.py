# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError


class Ir9421ExportWizard(models.TransientModel):
    _name = "ir9421.export.wizard"
    _description = "Export état 9421 IR (CSV annuel)"

    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )
    year = fields.Integer(
        string="Année fiscale",
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    file_data = fields.Binary(string="Fichier", readonly=True)
    file_name = fields.Char(string="Nom fichier", readonly=True)

    def action_export(self):
        self.ensure_one()
        if not self.env["res.company"]._is_morocco_payroll_company(self.company_id):
            raise UserError(_("Cette société n'est pas configurée pour la paie Maroc."))

        from datetime import date

        period_start = date(self.year, 1, 1)
        period_end = date(self.year, 12, 31)

        payslips = self.env["hr.payslip.ma"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("validated", "paid")),
                ("period_end", ">=", period_start),
                ("period_start", "<=", period_end),
            ]
        )

        by_employee = {}
        for slip in payslips:
            emp_id = slip.employee_id.id
            if emp_id not in by_employee:
                by_employee[emp_id] = {
                    "employee": slip.employee_id,
                    "brut": 0.0,
                    "ir": 0.0,
                    "months": 0,
                }
            by_employee[emp_id]["brut"] += slip.gross_salary
            ir_line = slip.line_ids.filtered(lambda l: l.code == "IR")[:1]
            by_employee[emp_id]["ir"] += ir_line.amount if ir_line else 0.0
            by_employee[emp_id]["months"] += 1

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "ANNEE",
            "CIN",
            "NOM",
            "N_CNSS",
            "BRUT_ANNUEL",
            "IR_RETENU_ANNUEL",
            "NB_MOIS",
            "SITUATION_FAMILIALE",
            "ENFANTS",
        ])

        for data in by_employee.values():
            emp = data["employee"]
            writer.writerow([
                self.year,
                emp.x_cin_number or "",
                emp.name or "",
                emp.x_cnss_number or "",
                "%.2f" % data["brut"],
                "%.2f" % data["ir"],
                data["months"],
                emp.marital or "",
                emp.children or 0,
            ])

        content = output.getvalue().encode("utf-8-sig")
        filename = "etat_9421_%s.csv" % self.year
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
