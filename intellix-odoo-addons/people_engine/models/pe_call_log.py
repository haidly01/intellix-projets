# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeCallLog(models.Model):
    _name = "pe.call.log"
    _description = "Journal des appels Call Center"
    _order = "date_call desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    profile_id = fields.Many2one(
        "pe.employee.profile",
        compute="_compute_profile_id",
        store=True,
        index=True,
    )
    lead_id = fields.Many2one("crm.lead", string="Lead CRM", index=True)
    campaign_id = fields.Many2one("pe.cc.campaign", string="Campagne", index=True)
    department_id = fields.Many2one("pe.department", required=True, index=True)

    date_call = fields.Datetime(
        string="Horodatage", default=fields.Datetime.now, required=True, index=True
    )
    duration = fields.Integer(string="Durée (sec)")
    duration_fmt = fields.Char(compute="_compute_duration_fmt")
    vicidial_id = fields.Char(string="ID VICIdial", index=True)

    outcome = fields.Selection(
        [
            ("interesse", "Intéressé"),
            ("pas_interesse", "Pas intéressé"),
            ("rappel", "Rappel planifié"),
            ("mauvais_num", "Mauvais numéro"),
            ("demo_bookee", "Démo bookée"),
            ("vendu", "Vente conclue"),
        ],
        required=True,
        default="interesse",
    )

    recording_url = fields.Char(string="URL enregistrement")
    transcript = fields.Text(string="Transcription IA")
    ai_score = fields.Float(string="Score IA (0-100)")
    ai_feedback = fields.Text(string="Coaching IA")
    ai_strengths = fields.Text(string="Points forts")
    ai_improvements = fields.Text(string="Axes amélioration")

    points_awarded = fields.Integer(string="Points attribués", readonly=True)
    badge_award_ids = fields.Many2many(
        "pe.badge.award",
        string="Badges déclenchés",
        readonly=True,
    )

    @api.depends("employee_id")
    def _compute_profile_id(self):
        Profile = self.env["pe.employee.profile"]
        for rec in self:
            profile = Profile.search(
                [("employee_id", "=", rec.employee_id.id)], limit=1
            )
            rec.profile_id = profile.id if profile else False

    @api.depends("duration")
    def _compute_duration_fmt(self):
        for rec in self:
            sec = rec.duration or 0
            rec.duration_fmt = "%sm %ss" % (sec // 60, sec % 60)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("department_id") and vals.get("employee_id"):
                profile = self.env["pe.employee.profile"].search(
                    [("employee_id", "=", vals["employee_id"])], limit=1
                )
                if profile and profile.department_pe_id:
                    vals["department_id"] = profile.department_pe_id.id
            if not vals.get("department_id"):
                template = self.env["pe.department"].search(
                    [("code", "=", "CC-TEMPLATE")], limit=1
                )
                if template:
                    vals["department_id"] = template.id
        records = super().create(vals_list)
        for rec in records:
            rec._award_gamification_points()
        return records

    def _award_gamification_points(self):
        self.ensure_one()
        engine = self.env["pe.gamification.engine"]
        pts = engine.award_call_log_points(self)
        self.points_awarded = pts
        if self.profile_id:
            badges = engine.check_callcenter_badges(self.profile_id, call_log=self)
            if badges:
                self.badge_award_ids = [(6, 0, badges.ids)]
