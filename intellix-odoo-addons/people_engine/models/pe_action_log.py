# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineActionLog(models.Model):
    _name = "pe.action.log"
    _description = "Journal actions RH People Engine"
    _order = "date desc, id desc"
    _rec_name = "description"

    profile_id = fields.Many2one("pe.employee.profile", ondelete="cascade", index=True)
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    action_type = fields.Selection(
        [
            ("score_calculated", "Score calculé"),
            ("objective_set", "Objectif défini"),
            ("praise_sent", "Félicitations envoyées"),
            ("coaching_started", "Coaching démarré"),
            ("warning_issued", "Avertissement émis"),
            ("pip_started", "Plan amélioration démarré"),
            ("termination_initiated", "Mise à pied initiée"),
            ("evaluation_completed", "Évaluation complétée"),
            ("badge_awarded", "Badge attribué"),
            ("status_changed", "Statut modifié"),
            ("document_sent", "Document envoyé"),
            ("document_acknowledged", "Document accusé réception"),
        ],
        required=True,
    )
    description = fields.Text(required=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    actor_id = fields.Many2one("res.users", string="Auteur")
    actor_type = fields.Selection(
        [
            ("system", "Système automatique"),
            ("hr", "Ressources humaines"),
            ("manager", "Gestionnaire"),
            ("dg", "Direction générale"),
        ],
        default="system",
    )
    evaluation_id = fields.Many2one("pe.evaluation", ondelete="set null")
    objective_id = fields.Many2one("pe.objective", ondelete="set null")
    score_before = fields.Float()
    score_after = fields.Float()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("pe_action_log_allow_write"):
            for vals in vals_list:
                if not vals.get("actor_id"):
                    vals["actor_id"] = self.env.user.id
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get("pe_action_log_allow_write") and not self.env.su:
            raise UserError(
                _("Le journal des actions RH est immuable et ne peut pas être modifié.")
            )
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("pe_action_log_allow_write") and not self.env.su:
            raise UserError(
                _("Le journal des actions RH est immuable et ne peut pas être supprimé.")
            )
        return super().unlink()

    @api.model
    def log_action(
        self,
        profile,
        action_type,
        description,
        actor_type="system",
        **kwargs,
    ):
        """Helper pour créer une entrée de journal."""
        return self.with_context(pe_action_log_allow_write=True).create(
            {
                "profile_id": profile.id,
                "action_type": action_type,
                "description": description,
                "actor_id": self.env.user.id if self.env.user else False,
                "actor_type": actor_type,
                **kwargs,
            }
        )
