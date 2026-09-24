# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PeAbsenceDetectedRiad(models.Model):
    _inherit = "pe.absence.detected"

    source_detection = fields.Selection(
        selection_add=[("riad_punch", "Pointage hébergement")],
        ondelete={"riad_punch": "cascade"},
    )
    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        compute="_compute_riad_establishment_id",
        store=True,
        index=True,
    )

    @api.depends("employee_id")
    def _compute_riad_establishment_id(self):
        Profile = self.env["pe.employee.profile"]
        for rec in self:
            profile = Profile.search(
                [
                    ("employee_id", "=", rec.employee_id.id),
                    ("riad_establishment_id", "!=", False),
                ],
                limit=1,
            )
            rec.riad_establishment_id = profile.riad_establishment_id


class PeAbsenceDetectionServiceRiad(models.AbstractModel):
    _inherit = "pe.absence.detection.service"

    @api.model
    def _active_employees(self):
        employees = super()._active_employees()
        riad_ids = (
            self.env["pe.employee.profile"]
            .sudo()
            .search([("riad_establishment_id", "!=", False)])
            .mapped("employee_id")
            .ids
        )
        if not riad_ids:
            return employees
        return employees.filtered(lambda emp: emp.id not in set(riad_ids))
