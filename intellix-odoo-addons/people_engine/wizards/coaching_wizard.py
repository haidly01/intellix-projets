# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineCoachingWizard(models.TransientModel):
    _name = "pe.coaching.wizard"
    _description = "Assistant coaching People Engine"

    profile_id = fields.Many2one("pe.employee.profile", required=True)
    wizard_mode = fields.Selection(
        [("session", "Session de coaching"), ("plan", "Plan de développement")],
        default="session",
        required=True,
    )
    session_type = fields.Selection(
        [
            ("praise", "Félicitations"),
            ("coaching", "Coaching développement"),
            ("warning", "Avertissement informel"),
            ("formal_warn", "Avertissement formel"),
            ("pip", "Plan d'amélioration (PIP)"),
            ("termination", "Dossier mise à pied"),
        ],
        default="coaching",
    )
    trigger_type = fields.Selection(
        [
            ("score_drop", "Baisse de score"),
            ("score_high", "Score exceptionnel"),
            ("objective_miss", "Objectif manqué"),
            ("objective_hit", "Objectif atteint"),
            ("manual", "Initié manuellement"),
        ],
        default="manual",
    )
    trigger_details = fields.Text(string="Notes contextuelles")
    use_ai = fields.Boolean(string="Générer avec Claude", default=True)
    compliance_preview = fields.Text(readonly=True)
    name = fields.Char(string="Titre du plan")
    plan_type = fields.Selection(
        [
            ("development", "Développement"),
            ("performance", "Performance"),
            ("onboarding", "Intégration"),
            ("promotion", "Promotion"),
            ("pip", "PIP"),
        ],
        default="development",
    )
    duration_days = fields.Selection(
        [("30", "30j"), ("60", "60j"), ("90", "90j"), ("180", "6 mois")],
        default="90",
    )
    score_target = fields.Float(string="Score cible")

    @api.onchange("session_type", "profile_id")
    def _onchange_compliance_preview(self):
        if self.wizard_mode != "session" or not self.profile_id:
            self.compliance_preview = False
            return
        if self.session_type not in ("formal_warn", "pip", "termination"):
            self.compliance_preview = False
            return
        session = self.env["pe.coaching.session"].new(
            {
                "profile_id": self.profile_id.id,
                "session_type": self.session_type,
                "manager_id": self.env.user.employee_id.id,
            }
        )
        result = self.env["pe.claude.coaching.service"].check_compliance(session)
        lines = []
        if result.get("blockers"):
            lines.append(_("BLOCAGES :") + "\n" + "\n".join(result["blockers"]))
        if result.get("warnings"):
            lines.append(_("AVERTISSEMENTS :") + "\n" + "\n".join(result["warnings"]))
        lines.append(self.env["pe.legal.engine"].DISCLAIMER)
        self.compliance_preview = "\n\n".join(lines)

    def action_create_learning_path(self):
        self.wizard_mode = "plan"
        return self.action_create()

    def action_create(self):
        self.ensure_one()
        manager = self.env.user.employee_id
        if not manager:
            raise UserError(_("Votre utilisateur doit être lié à un employé RH."))
        if self.wizard_mode == "plan":
            if self.use_ai:
                path = self.env["pe.lms.service"].generate_learning_path_with_claude(
                    self.profile_id, self.plan_type or "performance"
                )
            else:
                path = self.env["pe.learning.path"].create(
                    {
                        "profile_id": self.profile_id.id,
                        "manager_id": manager.id,
                        "name": self.name
                        or _("Parcours — %s") % self.profile_id.display_name,
                        "path_type": self.plan_type or "performance",
                        "duration_weeks": int(self.duration_days or "90") // 30 * 4
                        if self.duration_days
                        else 4,
                        "status": "pending",
                    }
                )
            return {
                "type": "ir.actions.act_window",
                "name": _("Parcours de formation"),
                "res_model": "pe.learning.path",
                "res_id": path.id,
                "view_mode": "form",
                "target": "current",
            }

        session = self.env["pe.coaching.session"].create(
            {
                "profile_id": self.profile_id.id,
                "manager_id": manager.id,
                "session_type": self.session_type,
                "trigger_type": self.trigger_type,
                "trigger_details": self.trigger_details,
                "trigger_score": self.profile_id.score_global,
            }
        )
        if self.use_ai:
            try:
                session.action_generate_claude()
            except UserError as exc:
                session.action_create_manual()
                raise UserError(
                    _("%s\n\nUne session manuelle a été créée.") % exc.args[0]
                ) from exc
        else:
            session.action_create_manual()
        return {
            "type": "ir.actions.act_window",
            "name": _("Session de coaching"),
            "res_model": "pe.coaching.session",
            "res_id": session.id,
            "view_mode": "form",
            "target": "current",
        }
