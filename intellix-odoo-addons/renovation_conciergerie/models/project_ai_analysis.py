import logging
import math
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

VELOCITY_WINDOW_DAYS = 30

ANALYSIS_SYSTEM = (
    "Tu es un directeur de projet expérimenté. À partir des indicateurs fournis, "
    "produis une analyse concise et actionnable : "
    "1) une évaluation de la santé du projet ; "
    "2) les 3 principaux risques ; "
    "3) 3 à 5 recommandations concrètes et priorisées ; "
    "4) un commentaire sur la date de fin prévue (réaliste / optimiste / à risque). "
    "Réponds en français, en HTML simple (titres <b>, listes <ul><li> ou <ol><li>). "
    "Sois direct et factuel, n'invente pas de données."
)


class ProjectAiAnalysis(models.Model):
    _inherit = "project.project"

    ai_health = fields.Selection(
        selection=[
            ("unknown", "Non analysé"),
            ("on_track", "Sur la bonne voie"),
            ("at_risk", "À risque"),
            ("critical", "Critique"),
        ],
        string="Santé (IA)",
        default="unknown",
        copy=False,
    )
    ai_predicted_end_date = fields.Date(
        string="Fin prévue (estimée)", copy=False
    )
    ai_analysis_html = fields.Html(
        string="Analyse IA", sanitize=True, copy=False
    )
    ai_analysis_date = fields.Datetime(
        string="Dernière analyse IA", readonly=True, copy=False
    )

    ai_open_count = fields.Integer(
        string="Tâches ouvertes", compute="_compute_ai_stats"
    )
    ai_overdue_count = fields.Integer(
        string="Tâches en retard", compute="_compute_ai_stats"
    )
    ai_completion_rate = fields.Float(
        string="Taux d'achèvement (%)", compute="_compute_ai_stats"
    )

    @api.depends(
        "task_ids",
        "task_ids.stage_id.fold",
        "task_ids.date_deadline",
        "task_ids.active",
    )
    def _compute_ai_stats(self):
        now = fields.Datetime.now()
        for project in self:
            tasks = project.task_ids
            total = len(tasks)
            done = len(tasks.filtered(lambda task: task.stage_id.fold))
            overdue = len(
                tasks.filtered(
                    lambda task: task.date_deadline
                    and task.date_deadline < now
                    and task.active
                    and not task.stage_id.fold
                )
            )
            project.ai_open_count = total - done
            project.ai_overdue_count = overdue
            project.ai_completion_rate = (done / total * 100.0) if total else 0.0

    def _compute_project_metrics(self):
        self.ensure_one()
        now = fields.Datetime.now()
        today = fields.Date.today()
        tasks = self.task_ids
        total = len(tasks)
        done_tasks = tasks.filtered(lambda task: task.stage_id.fold)
        open_tasks = tasks - done_tasks
        overdue = open_tasks.filtered(
            lambda task: task.date_deadline
            and task.date_deadline < now
            and task.active
        )
        completion = (len(done_tasks) / total * 100.0) if total else 0.0

        horizon = now - timedelta(days=VELOCITY_WINDOW_DAYS)
        closed_recent = done_tasks.filtered(
            lambda task: task.date_last_stage_update
            and task.date_last_stage_update >= horizon
        )
        per_day = len(closed_recent) / float(VELOCITY_WINDOW_DAYS)

        predicted_end = False
        if total and not open_tasks:
            predicted_end = today
        elif per_day > 0:
            predicted_end = today + timedelta(
                days=math.ceil(len(open_tasks) / per_day)
            )

        if not total:
            health = "unknown"
        elif not open_tasks:
            health = "on_track"
        else:
            ratio = len(overdue) / len(open_tasks)
            if ratio == 0:
                health = "on_track"
            elif ratio < 0.25:
                health = "at_risk"
            else:
                health = "critical"

        upcoming = open_tasks.filtered("date_deadline").sorted("date_deadline")[:5]
        return {
            "total": total,
            "done": len(done_tasks),
            "open": len(open_tasks),
            "overdue": len(overdue),
            "completion": completion,
            "velocity_30": len(closed_recent),
            "per_day": per_day,
            "predicted_end": predicted_end,
            "health": health,
            "upcoming": upcoming,
        }

    @staticmethod
    def _health_label(health):
        return {
            "unknown": _("Non analysé"),
            "on_track": _("Sur la bonne voie"),
            "at_risk": _("À risque"),
            "critical": _("Critique"),
        }.get(health, health)

    def _metrics_html(self, metrics):
        predicted = (
            metrics["predicted_end"].strftime("%d/%m/%Y")
            if metrics["predicted_end"]
            else _("indéterminée (vélocité insuffisante)")
        )
        upcoming_rows = "".join(
            "<li>%s — %s</li>"
            % (task.name, task.date_deadline.strftime("%d/%m/%Y"))
            for task in metrics["upcoming"]
        ) or "<li>%s</li>" % _("aucune échéance à venir")
        return (
            "<table class='table table-sm'>"
            "<tr><td>%s</td><td><b>%s</b></td></tr>"
            "<tr><td>%s</td><td>%s</td></tr>"
            "<tr><td>%s</td><td>%s</td></tr>"
            "<tr><td>%s</td><td>%s</td></tr>"
            "<tr><td>%s</td><td>%.0f%%</td></tr>"
            "<tr><td>%s</td><td>%s</td></tr>"
            "<tr><td>%s</td><td><b>%s</b></td></tr>"
            "</table>"
            "<p class='text-muted'>%s</p><ul>%s</ul>"
            % (
                _("Santé estimée"),
                self._health_label(metrics["health"]),
                _("Tâches totales"),
                metrics["total"],
                _("Terminées"),
                metrics["done"],
                _("En retard"),
                metrics["overdue"],
                _("Taux d'achèvement"),
                metrics["completion"],
                _("Vélocité (30 j)"),
                _("%s tâche(s) clôturée(s)") % metrics["velocity_30"],
                _("Fin prévue (estimée)"),
                predicted,
                _("Prochaines échéances :"),
                upcoming_rows,
            )
        )

    def action_ai_analyze_project(self):
        self.ensure_one()
        metrics = self._compute_project_metrics()
        metrics_html = self._metrics_html(metrics)
        narrative = ""

        if self.env["renovation.ai.service"]._available():
            predicted = (
                metrics["predicted_end"].strftime("%d/%m/%Y")
                if metrics["predicted_end"]
                else _("indéterminée")
            )
            prompt = _(
                "Projet : %(name)s\n"
                "Tâches totales : %(total)s\n"
                "Terminées : %(done)s\n"
                "Ouvertes : %(open)s\n"
                "En retard : %(overdue)s\n"
                "Taux d'achèvement : %(completion).0f%%\n"
                "Vélocité (30 derniers jours) : %(velocity)s tâche(s) clôturée(s)\n"
                "Date de fin prévue (heuristique) : %(predicted)s\n"
            ) % {
                "name": self.name,
                "total": metrics["total"],
                "done": metrics["done"],
                "open": metrics["open"],
                "overdue": metrics["overdue"],
                "completion": metrics["completion"],
                "velocity": metrics["velocity_30"],
                "predicted": predicted,
            }
            if metrics["upcoming"]:
                prompt += _("Prochaines échéances :\n")
                for task in metrics["upcoming"]:
                    prompt += "- %s (%s)\n" % (
                        task.name,
                        task.date_deadline.strftime("%d/%m/%Y"),
                    )
            answer = self.env["renovation.ai.service"]._call(
                [{"role": "user", "content": prompt}],
                system=self.env["renovation.ai.service"]._get_prompt(
                    "project_analysis", ANALYSIS_SYSTEM
                ),
                purpose="Analyse de projet — %s" % self.name,
            )
            narrative = (
                "<p><b>🤖 Analyse IA</b></p>%s<hr/>" % (answer or "")
            )
        else:
            narrative = (
                "<div class='alert alert-info'>%s</div>"
                % _(
                    "IA désactivée : analyse heuristique uniquement. "
                    "Activez l'IA dans les paramètres pour obtenir des "
                    "recommandations détaillées."
                )
            )

        self.write(
            {
                "ai_health": metrics["health"],
                "ai_predicted_end_date": metrics["predicted_end"] or False,
                "ai_analysis_html": narrative + metrics_html,
                "ai_analysis_date": fields.Datetime.now(),
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Analyse IA du projet"),
                "message": _("Analyse mise à jour (santé : %s).")
                % self._health_label(metrics["health"]),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
