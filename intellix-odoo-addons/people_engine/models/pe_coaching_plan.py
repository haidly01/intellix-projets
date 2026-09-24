# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineCoachingPlan(models.Model):
    _name = "pe.coaching.plan"
    _description = "Plan de développement People Engine"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    manager_id = fields.Many2one("hr.employee", string="Gestionnaire", required=True)

    name = fields.Char(required=True, tracking=True)
    plan_type = fields.Selection(
        [
            ("development", "Développement des compétences"),
            ("performance", "Amélioration performance"),
            ("onboarding", "Intégration nouveau"),
            ("promotion", "Préparation promotion"),
            ("pip", "Plan d'amélioration obligatoire"),
        ],
        default="development",
        required=True,
    )
    duration_days = fields.Selection(
        [
            ("30", "30 jours"),
            ("60", "60 jours"),
            ("90", "90 jours"),
            ("180", "6 mois"),
        ],
        default="90",
        required=True,
    )
    date_start = fields.Date(default=fields.Date.context_today)
    date_end = fields.Date(compute="_compute_date_end", store=True)
    score_at_start = fields.Float()
    score_current = fields.Float(related="profile_id.score_global")
    score_target = fields.Float()

    objective_ids = fields.One2many("pe.objective", "coaching_plan_id")
    claude_plan_content = fields.Html(
        string="Contenu du plan (Claude)", sanitize_attributes=False
    )
    claude_success_criteria = fields.Text(string="Critères de succès")
    claude_risk_factors = fields.Text(string="Facteurs de risque identifiés")
    progress_note_ids = fields.One2many("pe.plan.progress", "plan_id")
    completion_rate = fields.Float(compute="_compute_completion")

    status = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "En cours"),
            ("completed", "Complété"),
            ("failed", "Non atteint"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        tracking=True,
    )
    checkin_frequency = fields.Selection(
        [
            ("weekly", "Hebdomadaire"),
            ("biweekly", "Bimensuel"),
            ("monthly", "Mensuel"),
        ],
        default="weekly",
    )
    ai_generated = fields.Boolean(default=False, readonly=True)
    coaching_session_id = fields.Many2one(
        "pe.coaching.session",
        string="Session source",
        ondelete="set null",
    )
    due_date = fields.Date(
        string="Échéance",
        compute="_compute_due_date",
        store=True,
        readonly=False,
    )

    @api.depends("date_end")
    def _compute_due_date(self):
        for plan in self:
            plan.due_date = plan.date_end

    @api.model
    def get_dev_plan_header_data(self):
        """Stat cards header — Plans de développement."""
        plans = self.search([])
        active = plans.filtered(lambda p: p.status == "active")
        completed = plans.filtered(lambda p: p.status == "completed")
        rates = [p.completion_rate for p in active if p.completion_rate]
        return {
            "total": len(plans),
            "active": len(active),
            "completed": len(completed),
            "avg_completion": round(sum(rates) / len(rates)) if rates else 0,
        }

    @api.model
    def action_create_dev_plan(self):
        """Création rapide depuis empty state."""
        manager = self.env.user.employee_id
        if not manager:
            raise UserError(_("Aucun employé lié à votre utilisateur."))
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", manager.id)], limit=1
        )
        if not profile:
            raise UserError(_("Profil People Engine introuvable."))
        plan = self.create(
            {
                "name": _("Nouveau plan de développement"),
                "profile_id": profile.id,
                "manager_id": manager.id,
                "plan_type": "development",
                "status": "draft",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Plan de développement"),
            "res_model": "pe.coaching.plan",
            "res_id": plan.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.depends("date_start", "duration_days")
    def _compute_date_end(self):
        for plan in self:
            if plan.date_start and plan.duration_days:
                plan.date_end = plan.date_start + timedelta(
                    days=int(plan.duration_days)
                )
            else:
                plan.date_end = False

    @api.depends("objective_ids", "objective_ids.achievement_rate", "objective_ids.status")
    def _compute_completion(self):
        for plan in self:
            objs = plan.objective_ids.filtered(lambda o: o.status != "cancelled")
            if objs:
                plan.completion_rate = sum(objs.mapped("achievement_rate")) / len(
                    objs
                )
            else:
                plan.completion_rate = 0.0

    def action_generate_ai(self):
        self.ensure_one()
        if self.status != "draft":
            raise UserError(_("Seul un brouillon peut être régénéré par l'IA."))
        result = self.env["pe.claude.coaching.service"].generate_development_plan(
            self
        )
        self.write(
            {
                "name": result.get("title") or self.name,
                "claude_plan_content": result.get("content") or "",
                "claude_success_criteria": result.get("success_criteria") or "",
                "claude_risk_factors": result.get("risk_factors") or "",
                "score_at_start": self.profile_id.score_global,
                "ai_generated": True,
            }
        )
        return True

    def action_activate(self):
        for plan in self:
            plan.write({"status": "active"})
            plan.profile_id.write({"pe_status": "coaching"})
            self.env["pe.action.log"].log_action(
                plan.profile_id,
                "coaching_started",
                _("Plan de développement activé : %s") % plan.name,
                actor_type="manager",
            )

    def action_complete(self):
        self.write({"status": "completed"})

    def action_cancel(self):
        self.write({"status": "cancelled"})

    def action_open_from_profile(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Plan de développement"),
            "res_model": "pe.coaching.plan",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }
