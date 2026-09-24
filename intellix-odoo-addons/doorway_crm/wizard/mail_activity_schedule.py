# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwayMailActivitySchedule(models.TransientModel):
    _inherit = "mail.activity.schedule"

    doorway_scheduled_datetime = fields.Datetime(
        string="Date et heure",
        help="Planifier l'activité à une date et heure précises (calendrier).",
    )
    doorway_scheduled_duration = fields.Integer(
        string="Durée (minutes)",
        default=30,
    )

    @api.onchange("doorway_scheduled_datetime")
    def _onchange_doorway_scheduled_datetime(self):
        if self.doorway_scheduled_datetime:
            self.date_deadline = fields.Date.to_date(self.doorway_scheduled_datetime)

    def _action_schedule_activities(self):
        if self.doorway_scheduled_datetime:
            self.date_deadline = fields.Date.to_date(self.doorway_scheduled_datetime)
        activities = super()._action_schedule_activities()
        if self.doorway_scheduled_datetime:
            deadline = fields.Date.to_date(self.doorway_scheduled_datetime)
            activities.write(
                {
                    "doorway_scheduled_start": self.doorway_scheduled_datetime,
                    "doorway_scheduled_duration": self.doorway_scheduled_duration or 30,
                    "date_deadline": deadline,
                }
            )
        return activities
