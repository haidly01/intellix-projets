# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeopleEngineBadge(models.Model):
    _name = "pe.badge"
    _description = "Badge People Engine"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text()
    icon = fields.Char(default="🏆")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection(
        [
            ("performance", "Performance"),
            ("consistency", "Régularité"),
            ("teamwork", "Collaboration"),
            ("growth", "Progression"),
            ("leadership", "Leadership"),
            ("innovation", "Innovation"),
            ("milestone", "Étape clé"),
            ("special", "Spécial"),
        ],
        default="performance",
    )
    auto_award = fields.Boolean(
        default=True,
        help="Attribuer automatiquement quand les critères sont atteints.",
    )
    requires_manager_approval = fields.Boolean(
        default=True,
        help="Soumettre à approbation avant affichage à l'employé.",
    )
    criterion_type = fields.Selection(
        [
            ("score_above", "Score global au-dessus de X"),
            ("score_improvement", "Amélioration de X points"),
            ("crm_conversion", "Taux conversion CRM > X%"),
            ("crm_revenue", "Revenu généré > X$"),
            ("project_ontime", "Taux on-time > X%"),
            ("ia_quality", "Score qualité appels > X"),
            ("objective_complete", "Objectifs complétés (nombre)"),
            ("manual", "Attribution manuelle"),
            ("cc_first_sale", "CC — Première vente"),
            ("cc_demos_day", "CC — Démos sur une journée"),
            ("cc_calls_day", "CC — Appels sur une journée"),
            ("cc_ai_score_avg", "CC — Score IA moyen (N appels)"),
            ("cc_ai_perfect", "CC — Score IA parfait"),
            ("cc_monthly_objective", "CC — Objectif mensuel dépassé"),
            ("cc_presence_streak", "CC — Assiduité (jours)"),
            ("cc_monthly_objective", "CC — Objectif mensuel (%)"),
            ("cc_weekly_rank", "CC — Rang hebdomadaire"),
            ("cc_sale_after_18h", "CC — Vente après 18h"),
            ("cc_training_complete", "CC — Formation complète"),
            ("cc_team_help", "CC — Esprit d'équipe"),
        ],
        default="manual",
        required=True,
    )
    criterion_value = fields.Float(string="Seuil")
    points_value = fields.Integer(string="Points PE", default=10)
    karma_bonus = fields.Integer(
        string="Bonus karma Odoo",
        default=0,
        help="Points karma natifs (module gamification).",
    )
    rarity = fields.Selection(
        [
            ("common", "Commun"),
            ("uncommon", "Peu commun"),
            ("rare", "Rare"),
            ("epic", "Épique"),
            ("legendary", "Légendaire"),
        ],
        default="common",
    )
    award_ids = fields.One2many("pe.badge.award", "badge_id")
    times_awarded = fields.Integer(compute="_compute_times_awarded")

    _badge_code_unique = models.Constraint("unique(code)", "Le code du badge doit être unique.")

    @api.depends("award_ids")
    def _compute_times_awarded(self):
        for badge in self:
            badge.times_awarded = len(badge.award_ids)


class PeopleEngineBadgeAward(models.Model):
    _name = "pe.badge.award"
    _description = "Attribution de badge"
    _order = "award_date desc"

    badge_id = fields.Many2one("pe.badge", required=True, ondelete="restrict")
    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    award_date = fields.Datetime(default=fields.Datetime.now, required=True)
    awarded_by_id = fields.Many2one("hr.employee", string="Attribué par")
    awarded_by_system = fields.Boolean(default=False)
    reason = fields.Text()
    manager_approved = fields.Boolean(default=False)
    manager_id = fields.Many2one("hr.employee")
    approved_date = fields.Datetime()
    notified = fields.Boolean(default=False)
    notified_date = fields.Datetime()
    is_public = fields.Boolean(
        default=True,
        help="Visible par l'équipe dans le fil d'actualité.",
    )

    _profile_badge_unique = models.Constraint(
        "unique(profile_id, badge_id)",
        "Ce badge a déjà été attribué à cet employé.",
    )

    def action_manager_approve(self):
        for award in self:
            award.write(
                {
                    "manager_approved": True,
                    "manager_id": self.env.user.employee_id.id,
                    "approved_date": fields.Datetime.now(),
                }
            )
            award._apply_rewards()
            self.env["pe.action.log"].log_action(
                award.profile_id,
                "badge_awarded",
                _("Badge « %s » approuvé et publié") % award.badge_id.name,
                actor_type="manager",
            )

    def action_notify_employee(self):
        for award in self:
            if not award.manager_approved and award.badge_id.requires_manager_approval:
                raise UserError(_("Approuvez le badge avant notification."))
            partner = award.profile_id.user_id.partner_id
            if partner:
                award.profile_id.message_post(
                    body=_("Félicitations ! Vous avez obtenu le badge %s %s")
                    % (award.badge_id.icon, award.badge_id.name),
                    partner_ids=[partner.id],
                )
            award.write(
                {"notified": True, "notified_date": fields.Datetime.now()}
            )

    def _apply_rewards(self):
        self.env["pe.gamification.engine"]._add_points_for_badge(self)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for award in records:
            if not award.badge_id.requires_manager_approval:
                award.write({"manager_approved": True})
                award._apply_rewards()
        return records
