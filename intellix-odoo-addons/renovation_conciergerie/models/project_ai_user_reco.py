import logging
from collections import Counter
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

RECO_SYSTEM = (
    "Tu es un coach de productivité bienveillant et concret. À partir des tâches "
    "de l'utilisateur et de ses habitudes de travail, propose un PLAN D'ACTION "
    "priorisé pour aujourd'hui : par quoi commencer et pourquoi, en tenant compte "
    "des retards, des échéances proches, des priorités et d'une charge réaliste. "
    "Adapte le volume au rythme habituel de la personne (sa vélocité). "
    "Réponds en français, en HTML simple (liste numérotée <ol><li>), 8 actions "
    "maximum. N'invente pas de tâches."
)

VELOCITY_WINDOW_DAYS = 30


class ProjectAiUserReco(models.TransientModel):
    _name = "project.ai.user.reco"
    _description = "Recommandations IA personnalisées (habitudes)"

    user_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, readonly=True
    )
    summary_html = fields.Html(string="Votre tableau du jour", readonly=True)
    reco_html = fields.Html(string="Plan d'action recommandé", readonly=True)

    def _gather(self):
        user = self.env.user
        Task = self.env["project.task"]
        now = fields.Datetime.now()
        today = fields.Date.today()
        week = now + timedelta(days=7)

        open_tasks = Task.search(
            [
                ("user_ids", "in", user.id),
                ("active", "=", True),
                ("stage_id.fold", "=", False),
            ]
        )
        overdue = open_tasks.filtered(
            lambda task: task.date_deadline and task.date_deadline < now
        )
        due_today = open_tasks.filtered(
            lambda task: task.date_deadline
            and task.date_deadline >= now
            and task.date_deadline.date() == today
        )
        due_week = open_tasks.filtered(
            lambda task: task.date_deadline
            and task.date_deadline.date() > today
            and task.date_deadline <= week
        )
        high_priority = open_tasks.filtered(lambda task: task.priority in ("2", "3"))
        no_deadline = open_tasks.filtered(lambda task: not task.date_deadline)

        horizon = now - timedelta(days=VELOCITY_WINDOW_DAYS)
        closed_recent = Task.search_count(
            [
                ("user_ids", "in", user.id),
                ("stage_id.fold", "=", True),
                ("date_last_stage_update", ">=", horizon),
            ]
        )
        project_counter = Counter(open_tasks.mapped("project_id.name"))
        top_project = project_counter.most_common(1)
        top_project_name = top_project[0][0] if top_project else _("—")

        return {
            "open": open_tasks,
            "overdue": overdue,
            "due_today": due_today,
            "due_week": due_week,
            "high_priority": high_priority,
            "no_deadline": no_deadline,
            "velocity_30": closed_recent,
            "top_project": top_project_name,
        }

    @staticmethod
    def _task_lines(tasks, limit=8):
        rows = []
        for task in tasks[:limit]:
            deadline = (
                task.date_deadline.strftime("%d/%m/%Y")
                if task.date_deadline
                else ""
            )
            label = "%s — %s" % (task.project_id.name or "", task.name)
            if deadline:
                label += " (%s)" % deadline
            rows.append(label)
        return rows

    def _build_summary(self, data):
        def block(title, tasks, css):
            if not tasks:
                return ""
            items = "".join("<li>%s</li>" % line for line in self._task_lines(tasks))
            return (
                "<p class='%s mb-1'><b>%s (%s)</b></p><ul>%s</ul>"
                % (css, title, len(tasks), items)
            )

        return (
            "<p class='text-muted'>Rythme : <b>%s</b> tâche(s) clôturée(s) sur 30 j · "
            "Projet principal : <b>%s</b></p>"
            % (data["velocity_30"], data["top_project"])
            + block(_("En retard"), data["overdue"], "text-danger")
            + block(_("À échéance aujourd'hui"), data["due_today"], "text-warning")
            + block(_("Priorité haute / urgente"), data["high_priority"], "text-primary")
            + block(_("Cette semaine"), data["due_week"], "")
        )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        try:
            data = self._gather()
            values["summary_html"] = self._build_summary(data)
        except Exception as error:  # noqa: BLE001
            _logger.warning("Synthèse recommandations échouée : %s", error)
        return values

    def action_generate(self):
        self.ensure_one()
        data = self._gather()
        summary = self._build_summary(data)

        if not data["open"]:
            self.write(
                {
                    "summary_html": summary,
                    "reco_html": "<div class='alert alert-success'>%s</div>"
                    % _("Aucune tâche ouverte ne vous est assignée. Profitez-en !"),
                }
            )
            return self._reload_action()

        if self.env["renovation.ai.service"]._available():
            def bucket(title, tasks):
                if not tasks:
                    return ""
                return "%s :\n%s\n" % (
                    title,
                    "\n".join("- %s" % line for line in self._task_lines(tasks)),
                )

            prompt = _(
                "Utilisateur : %(user)s\n"
                "Rythme habituel : %(velocity)s tâche(s) clôturée(s) sur 30 jours\n"
                "Projet principal : %(project)s\n\n"
                "%(overdue)s%(today)s%(high)s%(week)s\n"
                "Propose un plan d'action priorisé pour aujourd'hui."
            ) % {
                "user": self.env.user.name,
                "velocity": data["velocity_30"],
                "project": data["top_project"],
                "overdue": bucket(_("EN RETARD"), data["overdue"]),
                "today": bucket(_("ÉCHÉANCE AUJOURD'HUI"), data["due_today"]),
                "high": bucket(_("PRIORITÉ HAUTE/URGENTE"), data["high_priority"]),
                "week": bucket(_("CETTE SEMAINE"), data["due_week"]),
            }
            answer = self.env["renovation.ai.service"]._call(
                [{"role": "user", "content": prompt}],
                system=self.env["renovation.ai.service"]._get_prompt(
                    "user_reco", RECO_SYSTEM
                ),
                purpose="Recommandations personnalisées — %s" % self.env.user.name,
            )
            reco = "<p><b>🤖 Votre plan d'action du jour</b></p>%s" % (answer or "")
        else:
            ordered = (
                data["overdue"]
                + data["due_today"]
                + data["high_priority"]
                + data["due_week"]
            )
            seen = set()
            lines = []
            for task in ordered:
                if task.id in seen:
                    continue
                seen.add(task.id)
                lines.append(self._task_lines(task)[0])
                if len(lines) >= 8:
                    break
            reco = (
                "<p><b>🤖 Votre plan d'action du jour (priorisation automatique)</b></p>"
                "<ol>%s</ol>" % "".join("<li>%s</li>" % line for line in lines)
            )

        self.write({"summary_html": summary, "reco_html": reco})
        return self._reload_action()

    def _reload_action(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.ai.user.reco",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Mes recommandations IA"),
        }
