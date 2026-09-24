import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CHAT_SYSTEM = (
    "Tu es l'assistant IA de gestion de projet de Doorway. Tu aides l'utilisateur "
    "à organiser son travail, prioriser ses tâches, rédiger des plans et répondre "
    "à ses questions sur ses projets. Sois concret, concis et bienveillant. "
    "Réponds en français. Utilise du HTML simple (paragraphes <p>, listes "
    "<ul>/<ol>) quand c'est utile. Tu ne peux pas modifier la base directement : "
    "propose des actions, l'utilisateur les exécute dans Odoo."
)

ASSIGNMENT_SYSTEM = (
    "Tu es un assistant de gestion de projet spécialisé dans l'attribution des "
    "tâches."
)


class ProjectAiChat(models.TransientModel):
    _name = "project.ai.chat"
    _description = "Assistant conversationnel IA"

    user_input = fields.Text(string="Votre message")
    conversation_html = fields.Html(string="Conversation", readonly=True)
    history_json = fields.Text(default="[]")

    def _user_context(self):
        Task = self.env["project.task"]
        now = fields.Datetime.now()
        week = now + timedelta(days=7)
        open_tasks = Task.search(
            [
                ("user_ids", "in", self.env.user.id),
                ("active", "=", True),
                ("stage_id.fold", "=", False),
            ],
            limit=50,
        )
        overdue = open_tasks.filtered(
            lambda task: task.date_deadline and task.date_deadline < now
        )
        soon = open_tasks.filtered(
            lambda task: task.date_deadline and now <= task.date_deadline <= week
        )
        lines = [
            _("Contexte utilisateur : %s") % self.env.user.name,
            _("Tâches ouvertes assignées : %s") % len(open_tasks),
            _("En retard : %s") % len(overdue),
            _("À échéance sous 7 jours : %s") % len(soon),
        ]
        if open_tasks:
            lines.append(_("Quelques tâches :"))
            for task in open_tasks[:15]:
                deadline = (
                    task.date_deadline.strftime("%d/%m/%Y")
                    if task.date_deadline
                    else "—"
                )
                lines.append(
                    "- [%s] %s (échéance %s)"
                    % (task.project_id.name or "?", task.name, deadline)
                )
        return "\n".join(lines)

    @staticmethod
    def _render(history):
        if not history:
            return (
                "<div class='text-muted'>%s</div>"
                % _("Posez une question sur vos projets et vos tâches.")
            )
        bubbles = []
        for message in history:
            is_user = message.get("role") == "user"
            align = "end" if is_user else "start"
            bg = "bg-primary text-white" if is_user else "bg-light"
            who = _("Vous") if is_user else _("Assistant IA")
            content = message.get("content") or ""
            if is_user:
                content = "<p class='mb-0'>%s</p>" % content
            bubbles.append(
                "<div class='d-flex justify-content-%s mb-2'>"
                "<div class='p-2 rounded %s' style='max-width:80%%;'>"
                "<small class='fw-bold d-block'>%s</small>%s</div></div>"
                % (align, bg, who, content)
            )
        return "<div>%s</div>" % "".join(bubbles)

    def action_send(self):
        self.ensure_one()
        message = (self.user_input or "").strip()
        if not message:
            raise UserError(_("Saisissez un message."))

        try:
            history = json.loads(self.history_json or "[]")
        except (ValueError, TypeError):
            history = []
        history.append({"role": "user", "content": message})

        system = "%s\n\n%s" % (
            self.env["renovation.ai.service"]._get_prompt("chat", CHAT_SYSTEM),
            self._user_context(),
        )
        answer = self.env["renovation.ai.service"]._call(
            history,
            system=system,
            purpose=_("Assistant conversationnel — %s") % self.env.user.name,
        )
        history.append({"role": "assistant", "content": answer or ""})

        self.write(
            {
                "history_json": json.dumps(history),
                "conversation_html": self._render(history),
                "user_input": False,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.ai.chat",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Assistant IA"),
        }

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        values["conversation_html"] = self._render([])
        return values
