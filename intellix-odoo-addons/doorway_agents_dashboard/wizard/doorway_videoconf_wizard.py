# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayVideoconfWizard(models.TransientModel):
    _name = "doorway.videoconf.wizard"
    _description = "Créer une visioconférence"

    meeting_type = fields.Selection(
        [
            ("instant", "Réunion instantanée"),
            ("scheduled", "Planifier pour plus tard"),
        ],
        string="Type",
        required=True,
        default="instant",
    )
    name = fields.Char(string="Titre", required=True, default="Visioconférence")
    start = fields.Datetime(
        string="Date et heure",
        default=lambda self: fields.Datetime.now(),
    )
    duration_minutes = fields.Integer(string="Durée (min)", default=30)
    partner_ids = fields.Many2many(
        "res.partner",
        string="Participants",
        domain=[("email", "!=", False)],
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        partner = self.env.user.partner_id
        if partner and "partner_ids" in fields_list:
            res["partner_ids"] = [(6, 0, [partner.id])]
        meeting_type = self.env.context.get("default_meeting_type")
        if meeting_type:
            res["meeting_type"] = meeting_type
        return res

    def _get_start_stop(self):
        self.ensure_one()
        duration = max(self.duration_minutes or 30, 15)
        if self.meeting_type == "instant":
            start = fields.Datetime.now()
        else:
            if not self.start:
                raise UserError(_("Indiquez la date et l'heure de la réunion."))
            start = self.start
        return start, start + timedelta(minutes=duration)

    def action_create(self):
        self.ensure_one()
        start, stop = self._get_start_stop()
        partner_ids = list(set(self.partner_ids.ids + [self.env.user.partner_id.id]))
        event = self.env["calendar.event"].doorway_create_meeting_with_videocall(
            name=self.name,
            start=start,
            stop=stop,
            partner_ids=partner_ids,
            user_id=self.env.user.id,
        )
        if self.meeting_type == "instant":
            return event._doorway_videocall_open_action()
        join_url = event.videocall_location or ""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Visioconférence planifiée"),
                "message": _(
                    "Rendez-vous créé. Partagez le lien : %(url)s"
                ) % {"url": join_url},
                "type": "success",
                "sticky": True,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "calendar.event",
                    "res_id": event.id,
                    "view_mode": "form",
                    "target": "current",
                },
            },
        }
