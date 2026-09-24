# -*- coding: utf-8 -*-
from odoo import fields, models

from odoo.addons.doorway_agents_dashboard.services.twilio_service import TwilioService


class DoorwayCallCoachingWizard(models.TransientModel):
    _name = "doorway.call.coaching.wizard"
    _description = "Coaching en direct"

    session_id = fields.Many2one("doorway.call.session", required=True)
    agent_id = fields.Many2one(related="session_id.agent_id")
    lead_id = fields.Many2one(related="session_id.lead_id")
    transcript = fields.Text(related="session_id.transcript")
    claude_suggestions = fields.Text(
        related="session_id.claude_analysis_realtime",
        string="Suggestions Claude",
    )
    supervisor_notes = fields.Text(string="Notes superviseur")
    transfer_number = fields.Char(string="Transférer vers")
    call_status = fields.Selection(related="session_id.call_status")

    def action_refresh_coaching(self):
        self.ensure_one()
        self.session_id.run_realtime_coaching()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_save_notes(self):
        self.ensure_one()
        self.session_id.write({"coaching_notes": self.supervisor_notes})
        return {"type": "ir.actions.act_window_close"}

    def action_transfer(self):
        self.ensure_one()
        if self.transfer_number and self.session_id.twilio_call_sid:
            TwilioService(self.env).transfer_call(
                self.session_id.twilio_call_sid, self.transfer_number
            )
        return {"type": "ir.actions.act_window_close"}

    def action_end_call(self):
        self.ensure_one()
        self.session_id.finalize_call()
        return {"type": "ir.actions.act_window_close"}

    def action_escalate(self):
        self.ensure_one()
        self.session_id.message_post(
            body="Escalade superviseur : %s" % (self.supervisor_notes or "—"),
            subtype_xmlid="mail.mt_note",
        )
        return {"type": "ir.actions.act_window_close"}
