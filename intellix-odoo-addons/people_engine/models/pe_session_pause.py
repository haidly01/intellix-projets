# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeSessionPause(models.Model):
    _name = "pe.session.pause"
    _description = "Pause agent call center"
    _order = "date_start desc"

    session_id = fields.Many2one(
        "doorway.vicidial.agent.session",
        string="Session",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        related="session_id.employee_id",
        store=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        related="session_id.user_id",
        store=True,
    )
    pause_type = fields.Selection(
        [
            ("pausette", "Pausette (5-15 min)"),
            ("dejeuner", "Déjeuner"),
            ("personnelle", "Personnelle"),
            ("autre", "Autre"),
        ],
        required=True,
        default="pausette",
    )
    date_start = fields.Datetime(
        string="Début", required=True, default=fields.Datetime.now
    )
    date_end = fields.Datetime(string="Fin")
    duration_seconds = fields.Integer(
        string="Durée (s)", compute="_compute_duration", store=True
    )
    state = fields.Selection(
        [("active", "En cours"), ("ended", "Terminée")],
        default="active",
        index=True,
    )
    is_deductible = fields.Boolean(
        string="Déductible paie",
        compute="_compute_is_deductible",
        store=True,
    )
    note = fields.Char()

    @api.depends("pause_type")
    def _compute_is_deductible(self):
        from odoo.addons.people_engine.services.disciplinary_config import SEUILS_PAUSES

        for rec in self:
            cfg = SEUILS_PAUSES.get(rec.pause_type, {})
            rec.is_deductible = cfg.get("deductible_paie", rec.pause_type != "dejeuner")

    @api.depends("date_start", "date_end", "state")
    def _compute_duration(self):
        now = fields.Datetime.now()
        for rec in self:
            end = rec.date_end or (now if rec.state == "active" else rec.date_start)
            if rec.date_start and end:
                rec.duration_seconds = max(
                    int((end - rec.date_start).total_seconds()), 0
                )
            else:
                rec.duration_seconds = 0

    def action_end_pause(self):
        for rec in self.filtered(lambda r: r.state == "active"):
            rec.write({"state": "ended", "date_end": fields.Datetime.now()})
