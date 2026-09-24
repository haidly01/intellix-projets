import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ProjectTaskFollowup(models.Model):
    _inherit = "project.task"

    is_overdue = fields.Boolean(
        string="En retard",
        compute="_compute_overdue",
        search="_search_is_overdue",
    )
    days_overdue = fields.Integer(
        string="Retard (jours)", compute="_compute_overdue"
    )
    overdue_alert_date = fields.Date(
        string="Dernière alerte de retard", readonly=True, copy=False
    )

    @api.depends("date_deadline", "stage_id.fold", "active")
    def _compute_overdue(self):
        now = fields.Datetime.now()
        today = fields.Date.today()
        for task in self:
            overdue = bool(
                task.date_deadline
                and task.date_deadline < now
                and task.active
                and not task.stage_id.fold
            )
            task.is_overdue = overdue
            task.days_overdue = (
                (today - task.date_deadline.date()).days if overdue else 0
            )

    def _search_is_overdue(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return []
        now = fields.Datetime.now()
        overdue_domain = [
            ("date_deadline", "!=", False),
            ("date_deadline", "<", now),
            ("stage_id.fold", "=", False),
        ]
        wants_overdue = (operator == "=") == value
        if wants_overdue:
            return overdue_domain
        return ["!", *overdue_domain]

    @api.model
    def _cron_alert_overdue_tasks(self):
        """Cron quotidien : alerte les assignés des tâches en retard."""
        now = fields.Datetime.now()
        today = fields.Date.today()
        tasks = self.search(
            [
                ("date_deadline", "!=", False),
                ("date_deadline", "<", now),
                ("active", "=", True),
            ]
        ).filtered(lambda task: not task.stage_id.fold)

        todo_type = self.env.ref(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        Activity = self.env["mail.activity"]
        alerted = 0
        for task in tasks:
            if task.overdue_alert_date == today:
                continue
            days = (today - task.date_deadline.date()).days
            deadline_label = fields.Datetime.context_timestamp(
                task, task.date_deadline
            ).strftime("%d/%m/%Y %H:%M")
            body = _(
                "⏰ <b>Tâche en retard</b> de %(days)s jour(s) "
                "(échéance : %(deadline)s)."
            ) % {"days": days, "deadline": deadline_label}
            task.message_post(body=body)
            if todo_type:
                for assignee in task.user_ids:
                    existing = Activity.search_count(
                        [
                            ("res_model", "=", "project.task"),
                            ("res_id", "=", task.id),
                            ("user_id", "=", assignee.id),
                            ("activity_type_id", "=", todo_type.id),
                        ]
                    )
                    if not existing:
                        task.activity_schedule(
                            "mail.mail_activity_data_todo",
                            user_id=assignee.id,
                            summary=_("Tâche en retard"),
                            note=body,
                        )
            task.overdue_alert_date = today
            alerted += 1
        _logger.info("Alertes de retard envoyées pour %s tâche(s).", alerted)
        return alerted
