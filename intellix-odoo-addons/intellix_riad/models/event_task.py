# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class IntellixRiadEventTask(models.Model):
    _name = "intellix.riad.event.task"
    _description = "Tâche de coordination événement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_deadline, sequence, id"

    name = fields.Char(string="Tâche", required=True, tracking=True)
    event_id = fields.Many2one(
        "intellix.riad.event",
        required=True,
        ondelete="cascade",
        index=True,
    )
    establishment_id = fields.Many2one(
        related="event_id.establishment_id",
        store=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    assignee_id = fields.Many2one(
        "pe.employee.profile",
        string="Responsable",
        tracking=True,
        domain="[('riad_establishment_id', '=', establishment_id)]",
    )
    date_deadline = fields.Date(string="Échéance", tracking=True, index=True)
    state = fields.Selection(
        [
            ("todo", "À faire"),
            ("doing", "En cours"),
            ("done", "Fait"),
        ],
        default="todo",
        required=True,
        tracking=True,
        index=True,
    )
    reminder_sent_on = fields.Date(string="Dernier rappel", readonly=True, copy=False)
    is_late = fields.Boolean(compute="_compute_is_late")
    assignee_initial = fields.Char(compute="_compute_assignee_initial")

    @api.depends("date_deadline", "state")
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_late = bool(
                rec.date_deadline
                and rec.state != "done"
                and rec.date_deadline < today
            )

    @api.depends("assignee_id.display_name")
    def _compute_assignee_initial(self):
        for rec in self:
            name = rec.assignee_id.display_name or rec.assignee_id.employee_id.name or ""
            rec.assignee_initial = (name[:1] or "?").upper()

    def _assignee_email(self):
        self.ensure_one()
        profile = self.assignee_id
        if not profile:
            return False
        return profile.user_id.email or profile.employee_id.work_email or False

    @api.model
    def cron_send_deadline_reminders(self):
        today = fields.Date.context_today(self)
        tasks = self.search(
            [
                ("state", "!=", "done"),
                ("date_deadline", "!=", False),
                ("date_deadline", "<=", today),
                ("assignee_id", "!=", False),
                "|",
                ("reminder_sent_on", "=", False),
                ("reminder_sent_on", "<", today),
            ]
        )
        from odoo.addons.doorway_messaging.services.email_service import EmailService

        mailer = EmailService(self.env)
        for task in tasks:
            email = task._assignee_email()
            due = task.date_deadline.strftime("%d/%m/%Y")
            late = "en retard" if task.is_late else "arrivée à échéance"
            subject = "Rappel tâche événement — %s" % (task.event_id.name or "Événement")
            body = (
                "<p>Tâche <strong>%s</strong> %s (%s).</p>"
                "<p>Événement : %s<br/>Établissement : %s</p>"
                % (
                    task.name,
                    late,
                    due,
                    task.event_id.name or "",
                    task.establishment_id.name or "",
                )
            )
            if email:
                result = mailer.send_email(
                    email,
                    subject,
                    body,
                    recipient_name=task.assignee_id.display_name or "",
                )
                if not result.get("success"):
                    _logger.warning(
                        "Rappel tâche %s: %s", task.id, result.get("error")
                    )
                    continue
            task.event_id.message_post(body="%s — %s (%s)." % (subject, task.name, due))
            task.reminder_sent_on = today
