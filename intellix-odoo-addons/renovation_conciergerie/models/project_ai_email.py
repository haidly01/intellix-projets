import logging
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

from .project_ai_task import MAX_TASKS, SYSTEM_PROMPT

_logger = logging.getLogger(__name__)


class ProjectProjectAiEmail(models.Model):
    _inherit = "project.project"

    ai_email_to_tasks = fields.Boolean(
        string="Générer des tâches via l'IA depuis les e-mails",
        help="Quand un e-mail arrive sur l'alias de ce projet, l'IA en extrait "
        "automatiquement des tâches, créées en sous-tâches de l'e-mail reçu.",
    )

    def _ai_generate_tasks_from_text(
        self, source_text, source_label=None, parent_task=None
    ):
        """Génère et crée des tâches à partir d'un texte libre via l'IA.

        Renvoie le recordset des tâches créées. Conçu pour les flux automatiques
        (e-mails) : aucune étape de révision.
        """
        self.ensure_one()
        Task = self.env["project.task"]
        if not source_text or not source_text.strip():
            return Task
        if not self.env["renovation.ai.service"]._available():
            return Task

        users = self.env["res.users"]
        if self.user_id:
            users |= self.user_id
        users |= self.task_ids.mapped("user_ids")
        users |= self.collaborator_ids.mapped("partner_id.user_ids")
        candidates = users.filtered(lambda u: u.active and u.share is False)
        names_lower = {u.name.lower(): u.id for u in candidates}
        members = ", ".join(candidates.mapped("name")) or _("(aucun membre)")

        user_content = _(
            "Projet : %(project)s\n"
            "Date du jour : %(today)s\n"
            "Membres disponibles pour l'assignation : %(members)s\n\n"
            "Source (%(label)s) à transformer en tâches :\n%(text)s"
        ) % {
            "project": self.name,
            "today": fields.Date.context_today(self).isoformat(),
            "members": members,
            "label": source_label or _("texte"),
            "text": source_text,
        }
        answer = self.env["renovation.ai.service"]._call(
            [{"role": "user", "content": user_content}],
            system=self.env["renovation.ai.service"]._get_prompt(
                "task_generation", SYSTEM_PROMPT
            ),
            purpose="Génération de tâches (e-mail) — projet %s" % self.name,
        )

        try:
            items = self.env["project.ai.task.wizard"]._extract_json(answer)
        except Exception:  # noqa: BLE001
            _logger.warning("Parsing IA (e-mail) échoué pour projet %s", self.name)
            return Task
        if not isinstance(items, list):
            return Task

        today = fields.Date.context_today(self)
        created = Task
        for item in items[:MAX_TASKS]:
            if not isinstance(item, dict):
                continue
            title = (item.get("titre") or item.get("title") or "").strip()
            if not title:
                continue
            assignee_id = False
            assignee_name = (item.get("assigne") or item.get("assignee") or "").strip()
            if assignee_name:
                key = assignee_name.lower()
                assignee_id = names_lower.get(key)
                if not assignee_id:
                    for cand_name, cand_id in names_lower.items():
                        if key in cand_name or cand_name in key:
                            assignee_id = cand_id
                            break
            try:
                days = int(item.get("jours") or item.get("days") or 0)
            except (TypeError, ValueError):
                days = 0
            priority = str(item.get("priorite") or item.get("priority") or "0")
            if priority not in ("0", "1", "2", "3"):
                priority = "0"
            vals = {
                "name": title[:250],
                "project_id": self.id,
                "priority": priority,
            }
            description = (item.get("description") or "").strip()
            if description:
                vals["description"] = "<p>%s</p>" % description.replace("\n", "<br/>")
            if days and days > 0:
                vals["date_deadline"] = datetime.combine(
                    today + timedelta(days=days), time(17, 0)
                )
            if assignee_id:
                vals["user_ids"] = [(4, assignee_id)]
            if parent_task:
                vals["parent_id"] = parent_task.id
            created |= Task.create(vals)
        return created


class ProjectTaskAiEmail(models.Model):
    _inherit = "project.task"

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        task = super().message_new(msg_dict, custom_values=custom_values)
        project = task.project_id
        if not project or not project.ai_email_to_tasks:
            return task
        try:
            if not self.env["renovation.ai.service"]._available():
                return task
            subject = msg_dict.get("subject") or ""
            body = self._html_to_text(msg_dict.get("body") or "")
            source_text = ("%s\n\n%s" % (subject, body)).strip()
            created = project.sudo()._ai_generate_tasks_from_text(
                source_text, source_label=_("e-mail entrant"), parent_task=task
            )
            if created:
                task.message_post(
                    body=_(
                        "🤖 %s sous-tâche(s) générée(s) automatiquement par l'IA "
                        "à partir de cet e-mail."
                    )
                    % len(created)
                )
        except Exception as error:  # noqa: BLE001
            _logger.warning("E-mail → tâches IA échoué : %s", error)
            task.message_post(
                body=_(
                    "⚠️ La génération automatique de tâches par l'IA a échoué : %s"
                )
                % error
            )
        return task
