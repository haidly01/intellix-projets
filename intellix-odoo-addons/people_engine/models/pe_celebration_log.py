# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .pe_celebration_template import PeCelebrationTemplate


class PeCelebrationLog(models.Model):
    _name = "pe.celebration.log"
    _description = "Historique des félicitations RH"
    _order = "sent_at desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
        ondelete="cascade",
        index=True,
    )
    profile_id = fields.Many2one(
        "pe.employee.profile",
        ondelete="set null",
        index=True,
    )
    occasion_type = fields.Selection(
        selection=PeCelebrationTemplate.OCCASION_TYPES,
        required=True,
        index=True,
    )
    occasion_date = fields.Date(required=True, index=True)
    occasion_year = fields.Integer(
        compute="_compute_occasion_year",
        store=True,
        index=True,
    )
    template_id = fields.Many2one(
        "pe.celebration.template",
        ondelete="set null",
    )
    detail = fields.Text(string="Détail")
    email_sent = fields.Boolean(default=False)
    notification_sent = fields.Boolean(default=False)
    sent_at = fields.Datetime(default=fields.Datetime.now, index=True)

    _celebration_unique_year = models.UniqueIndex(
        "(employee_id, occasion_type, occasion_year)"
        " WHERE occasion_type NOT IN ('custom', 'praise')",
        "Une félicitation de ce type a déjà été envoyée pour cet employé cette année.",
    )

    @api.depends("occasion_date")
    def _compute_occasion_year(self):
        for rec in self:
            rec.occasion_year = rec.occasion_date.year if rec.occasion_date else 0
