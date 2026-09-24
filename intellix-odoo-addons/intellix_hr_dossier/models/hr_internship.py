# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrInternship(models.Model):
    _name = "hr.internship"
    _description = "Stage / Internship"
    _order = "date_start desc, id desc"

    name = fields.Char(
        string="Référence",
        compute="_compute_name",
        store=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Stagiaire",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="employee_id.company_id",
        store=True,
        readonly=True,
    )
    date_start = fields.Date(string="Date début", required=True)
    date_end = fields.Date(string="Date fin")
    supervisor_id = fields.Many2one(
        "hr.employee",
        string="Encadrant",
        domain="[('company_id', '=', company_id)]",
    )
    mission_description = fields.Text(string="Description de la mission")
    establishment = fields.Char(
        string="Établissement",
        help="École, université ou organisme d'accueil du stage.",
    )
    active = fields.Boolean(default=True)

    @api.depends("employee_id", "date_start", "establishment")
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.employee_id:
                parts.append(rec.employee_id.name)
            if rec.establishment:
                parts.append(rec.establishment)
            elif rec.date_start:
                parts.append(str(rec.date_start))
            rec.name = " — ".join(parts) or _("Stage")

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError(
                    _("La date de fin doit être postérieure à la date de début.")
                )
