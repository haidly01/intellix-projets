import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class RenovationAiPrompt(models.Model):
    """Prompts système éditables (affinage du comportement de l'IA).

    Chaque fonctionnalité IA lit son prompt système ici (via
    ``renovation.ai.service._get_prompt``) avec un repli sur la valeur par
    défaut codée. Les administrateurs peuvent ainsi ajuster le ton et les
    consignes sans modifier le code.
    """

    _name = "renovation.ai.prompt"
    _description = "Prompt système IA (éditable)"
    _order = "name"

    code = fields.Char(string="Code", required=True, index=True)
    name = fields.Char(string="Nom", required=True)
    system_prompt = fields.Text(string="Prompt système", required=True)
    active = fields.Boolean(string="Actif", default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code du prompt doit être unique."),
    ]

    @api.model
    def _default_prompts(self):
        from .project_ai_task import SYSTEM_PROMPT
        from .project_ai_assistant import (
            ASSIGNMENT_SYSTEM,
            NEXT_STEPS_SYSTEM,
            SUMMARY_SYSTEM,
        )
        from .project_ai_analysis import ANALYSIS_SYSTEM
        from .project_ai_user_reco import RECO_SYSTEM
        from .project_ai_chat import CHAT_SYSTEM

        return {
            "task_generation": (_("Génération de tâches"), SYSTEM_PROMPT),
            "task_summary": (_("Assistant : résumé de tâche"), SUMMARY_SYSTEM),
            "task_next_steps": (
                _("Assistant : prochaines étapes"),
                NEXT_STEPS_SYSTEM,
            ),
            "assignment": (_("Suggestion d'assignation"), ASSIGNMENT_SYSTEM),
            "project_analysis": (_("Analyse de projet"), ANALYSIS_SYSTEM),
            "user_reco": (_("Recommandations personnalisées"), RECO_SYSTEM),
            "chat": (_("Assistant conversationnel"), CHAT_SYSTEM),
        }

    @api.model
    def _seed_defaults(self):
        existing = set(self.search([]).mapped("code"))
        for code, (name, prompt) in self._default_prompts().items():
            if code not in existing:
                self.create(
                    {"code": code, "name": name, "system_prompt": prompt}
                )
        return True

    def action_reset_default(self):
        defaults = self._default_prompts()
        for record in self:
            entry = defaults.get(record.code)
            if entry:
                record.system_prompt = entry[1]
        return True
