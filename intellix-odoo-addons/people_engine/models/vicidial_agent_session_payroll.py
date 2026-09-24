# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class VicidialAgentSessionPayroll(models.Model):
    _inherit = "doorway.vicidial.agent.session"

    pause_ids = fields.One2many("pe.session.pause", "session_id", string="Pauses")
    active_pause_id = fields.Many2one(
        "pe.session.pause",
        string="Pause en cours",
        compute="_compute_active_pause",
    )
    current_pause_type = fields.Char(compute="_compute_active_pause")
    pause_seconds_current = fields.Integer(compute="_compute_active_pause")
    nb_pauses = fields.Integer(compute="_compute_pause_stats")
    pause_deductible_seconds = fields.Integer(compute="_compute_pause_stats")

    def _compute_active_pause(self):
        Pause = self.env["pe.session.pause"].sudo()
        now = fields.Datetime.now()
        for rec in self:
            pause = Pause.search(
                [("session_id", "=", rec.id), ("state", "=", "active")],
                limit=1,
            )
            rec.active_pause_id = pause.id if pause else False
            rec.current_pause_type = pause.pause_type if pause else ""
            if pause and pause.date_start:
                rec.pause_seconds_current = int(
                    (now - pause.date_start).total_seconds()
                )
            else:
                rec.pause_seconds_current = 0

    def _compute_pause_stats(self):
        for rec in self:
            pauses = rec.pause_ids.filtered(lambda p: p.state == "ended")
            rec.nb_pauses = len(pauses)
            rec.pause_deductible_seconds = sum(
                p.duration_seconds for p in pauses if p.is_deductible
            )

    def _end_active_pause(self):
        Pause = self.env["pe.session.pause"].sudo()
        for rec in self:
            active = Pause.search(
                [("session_id", "=", rec.id), ("state", "=", "active")]
            )
            active.action_end_pause()

    def _start_typed_pause(self, pause_type):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("La session n'est pas active."))
        self._end_active_pause()
        if self.vicidial_user:
            self._vicidial_svc().set_agent_paused(self.vicidial_user)
        pause = self.env["pe.session.pause"].sudo().create(
            {
                "session_id": self.id,
                "pause_type": pause_type,
                "date_start": fields.Datetime.now(),
            }
        )
        self.write(
            {
                "state": "paused",
                "last_pause_start": fields.Datetime.now(),
            }
        )
        labels = {
            "pausette": _("Pausette"),
            "dejeuner": _("Déjeuner"),
            "personnelle": _("Pause personnelle"),
        }
        self._log_presence(
            "en_pause",
            "%s — %s" % (labels.get(pause_type, pause_type), self.campaign_id.name),
        )
        return pause

    def action_pause_pausette(self):
        self.ensure_one()
        self._start_typed_pause("pausette")
        return self._to_client_dict()

    def action_pause_dejeuner(self):
        self.ensure_one()
        self._start_typed_pause("dejeuner")
        return self._to_client_dict()

    def action_pause_personnelle(self):
        self.ensure_one()
        self._start_typed_pause("personnelle")
        return self._to_client_dict()

    def action_pause_session(self):
        self._end_active_pause()
        res = super().action_pause_session()
        for rec in self.filtered(lambda r: r.state == "paused"):
            active = self.env["pe.session.pause"].sudo().search(
                [("session_id", "=", rec.id), ("state", "=", "active")],
                limit=1,
            )
            if not active:
                self.env["pe.session.pause"].sudo().create(
                    {
                        "session_id": rec.id,
                        "pause_type": "autre",
                        "date_start": fields.Datetime.now(),
                    }
                )
        return res

    def action_resume_session(self):
        self._end_active_pause()
        return super().action_resume_session()

    def action_end_session(self):
        self._end_active_pause()
        res = super().action_end_session()
        try:
            self.env["pe.timesheet.bridge.service"].sudo().log_session_to_timesheet(
                self
            )
        except Exception:  # noqa: BLE001
            pass
        return res

    def _to_client_dict(self, vicidial_live=None):
        data = super()._to_client_dict(vicidial_live)
        self.ensure_one()
        data["current_pause_type"] = self.current_pause_type or ""
        data["pause_seconds_current"] = self.pause_seconds_current or 0
        data["nb_pauses"] = self.nb_pauses or 0
        return data
