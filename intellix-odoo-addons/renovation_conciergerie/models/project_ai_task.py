import json
import logging
import re
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_TASKS = 20

SYSTEM_PROMPT = (
    "Tu es un chef de projet expérimenté. À partir d'un brief (note, e-mail, "
    "compte-rendu, document), tu produis une liste de tâches concrètes, "
    "actionnables et bien découpées pour Odoo Projet. "
    "Réponds UNIQUEMENT avec un tableau JSON valide (aucun texte autour, pas de "
    "balises markdown). Chaque élément est un objet : "
    '{"titre": str, "description": str (1-3 phrases, étapes clés), '
    '"jours": int (échéance suggérée en nombre de jours à partir d\'aujourd\'hui, '
    "0 si non pertinent), "
    '"priorite": "0"|"1"|"2"|"3" (0=basse, 1=moyenne, 2=haute, 3=urgente), '
    '"assigne": str (nom EXACT d\'un membre de la liste fournie, ou "" si incertain)}. '
    "Maximum %s tâches. Écris en français."
) % MAX_TASKS


class ProjectAiTaskWizard(models.TransientModel):
    _name = "project.ai.task.wizard"
    _description = "Génération de tâches par IA"

    project_id = fields.Many2one(
        "project.project", string="Projet", required=True, ondelete="cascade"
    )
    source_text = fields.Text(
        string="Brief / e-mail / document",
        help="Collez ici le brief, l'e-mail, le compte-rendu ou le document à "
        "transformer en tâches.",
    )
    extra_instructions = fields.Char(
        string="Instructions supplémentaires (optionnel)",
        help="Ex : 'découpe en jalons hebdomadaires', 'priorise la conformité'…",
    )
    state = fields.Selection(
        selection=[("input", "Saisie"), ("review", "Révision")],
        default="input",
        string="Étape",
    )
    line_ids = fields.One2many(
        "project.ai.task.wizard.line", "wizard_id", string="Tâches proposées"
    )

    def _candidate_users(self):
        self.ensure_one()
        users = self.env["res.users"]
        if self.project_id.user_id:
            users |= self.project_id.user_id
        tasks = self.env["project.task"].search(
            [("project_id", "=", self.project_id.id)]
        )
        users |= tasks.mapped("user_ids")
        users |= self.project_id.collaborator_ids.mapped("partner_id.user_ids")
        return users.filtered(lambda u: u.active)

    @staticmethod
    def _extract_json(raw):
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if match:
            text = match.group(1)
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("taches", "tasks", "items", "resultats"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        return data

    def action_generate(self):
        self.ensure_one()
        if not self.source_text or not self.source_text.strip():
            raise UserError(_("Veuillez saisir un brief à transformer en tâches."))

        candidates = self._candidate_users()
        names = ", ".join(candidates.mapped("name")) or _("(aucun membre identifié)")
        user_content = _(
            "Projet : %(project)s\n"
            "Date du jour : %(today)s\n"
            "Membres disponibles pour l'assignation : %(members)s\n"
        ) % {
            "project": self.project_id.name,
            "today": fields.Date.context_today(self).isoformat(),
            "members": names,
        }
        if self.extra_instructions:
            user_content += _("Consignes : %s\n") % self.extra_instructions
        user_content += _("\nBrief à transformer en tâches :\n%s") % self.source_text

        answer = self.env["renovation.ai.service"]._call(
            [{"role": "user", "content": user_content}],
            system=self.env["renovation.ai.service"]._get_prompt(
                "task_generation", SYSTEM_PROMPT
            ),
            purpose=_("Génération de tâches — projet %s") % self.project_id.name,
        )

        try:
            items = self._extract_json(answer)
        except (ValueError, json.JSONDecodeError) as error:
            _logger.warning("Parsing IA tâches échoué : %s", error)
            raise UserError(
                _(
                    "La réponse de l'IA n'a pas pu être interprétée. "
                    "Réessayez ou reformulez le brief.\n\nRéponse brute :\n%s"
                )
                % (answer or "")[:1000]
            )
        if not isinstance(items, list) or not items:
            raise UserError(_("L'IA n'a proposé aucune tâche. Reformulez le brief."))

        names_lower = {u.name.lower(): u.id for u in candidates}
        lines = []
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
            deadline = False
            if days and days > 0:
                deadline = fields.Date.context_today(self) + timedelta(days=days)
            priority = str(item.get("priorite") or item.get("priority") or "0")
            if priority not in ("0", "1", "2", "3"):
                priority = "0"
            lines.append(
                (
                    0,
                    0,
                    {
                        "selected": True,
                        "name": title[:250],
                        "description": (item.get("description") or "").strip(),
                        "deadline": deadline,
                        "priority": priority,
                        "user_id": assignee_id,
                    },
                )
            )

        if not lines:
            raise UserError(_("L'IA n'a proposé aucune tâche exploitable."))

        self.line_ids = [(5, 0, 0)] + lines
        self.state = "review"
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.ai.task.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Tâches proposées par l'IA"),
        }

    def action_create_tasks(self):
        self.ensure_one()
        lines = self.line_ids.filtered("selected")
        if not lines:
            raise UserError(_("Sélectionnez au moins une tâche à créer."))
        Task = self.env["project.task"]
        created = Task
        for line in lines:
            vals = {
                "name": line.name,
                "project_id": self.project_id.id,
                "priority": line.priority,
            }
            if line.description:
                vals["description"] = "<p>%s</p>" % line.description.replace(
                    "\n", "<br/>"
                )
            if line.deadline:
                vals["date_deadline"] = datetime.combine(line.deadline, time(17, 0))
            if line.user_id:
                vals["user_ids"] = [(4, line.user_id.id)]
            created |= Task.create(vals)
        return {
            "type": "ir.actions.act_window",
            "name": _("Tâches créées par l'IA"),
            "res_model": "project.task",
            "domain": [("id", "in", created.ids)],
            "view_mode": "list,form,kanban",
            "context": {"default_project_id": self.project_id.id},
        }


class ProjectAiTaskWizardLine(models.TransientModel):
    _name = "project.ai.task.wizard.line"
    _description = "Tâche proposée par l'IA"

    wizard_id = fields.Many2one(
        "project.ai.task.wizard", required=True, ondelete="cascade"
    )
    selected = fields.Boolean(string="Créer", default=True)
    name = fields.Char(string="Titre", required=True)
    description = fields.Text(string="Description")
    deadline = fields.Date(string="Échéance")
    priority = fields.Selection(
        selection=[
            ("0", "Basse"),
            ("1", "Moyenne"),
            ("2", "Haute"),
            ("3", "Urgente"),
        ],
        default="0",
        string="Priorité",
    )
    user_id = fields.Many2one("res.users", string="Assigné suggéré")


class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_open_ai_task_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Générer des tâches (IA)"),
            "res_model": "project.ai.task.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }
