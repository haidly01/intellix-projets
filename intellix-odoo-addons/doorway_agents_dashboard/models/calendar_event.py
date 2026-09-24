# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    doorway_agent_profile_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA",
        ondelete="set null",
        index=True,
    )

    @api.model
    def doorway_create_meeting_with_videocall(
        self,
        name,
        start,
        stop,
        partner_ids,
        user_id=None,
        agent_profile_id=None,
        description=None,
    ):
        """Crée un rendez-vous avec visioconférence Discuss."""
        vals = {
            "name": name,
            "start": start,
            "stop": stop,
            "partner_ids": [(6, 0, partner_ids)],
            "show_as": "busy",
            "privacy": "public",
        }
        if user_id:
            vals["user_id"] = user_id
        if agent_profile_id:
            vals["doorway_agent_profile_id"] = agent_profile_id
        if description:
            vals["description"] = description
        event = self.create(vals)
        event._set_discuss_videocall_location()
        return event

    @api.model
    def action_doorway_instant_videocall(self):
        """Crée une visio immédiate et ouvre le lien Discuss."""
        now = fields.Datetime.now()
        event = self.doorway_create_meeting_with_videocall(
            name=_("Visioconférence"),
            start=now,
            stop=now + timedelta(minutes=30),
            partner_ids=[self.env.user.partner_id.id],
            user_id=self.env.user.id,
        )
        return event._doorway_videocall_open_action()

    def _doorway_videocall_open_action(self):
        self.ensure_one()
        url = self.videocall_location
        if not url:
            raise UserError(_("Impossible de générer le lien de visioconférence."))
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }
