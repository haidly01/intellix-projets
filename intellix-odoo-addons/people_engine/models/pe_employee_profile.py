# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

from odoo.addons.people_engine.services.alert_service import PeopleEngineAlertService
from odoo.addons.people_engine.services.collector_service import PeopleEngineCollector
from odoo.addons.people_engine.services.score_engine import PeopleEngineScoreEngine

# Groupes Doorway / IntelliX assignables depuis la fiche profil (hors RH PE et sync auto).
DOORWAY_PERMISSION_GROUP_XMLIDS = (
    "renovation_conciergerie.group_agence_doorway_crm",
    "renovation_conciergerie.group_agence_doorway_crm_sales",
    "renovation_conciergerie.group_pipeline_supervisor",
    "renovation_conciergerie.group_pipeline_admin",
    "renovation_conciergerie.group_automation_configurator",
    "doorway_vicidial_campaigns.group_vicidial_qualifier",
    "doorway_vicidial_campaigns.group_vicidial_supervisor",
    "doorway_agents_dashboard.group_doorway_agent_viewer",
    "doorway_agents_dashboard.group_doorway_agent_tester",
    "doorway_agents_dashboard.group_doorway_agent_manager",
    "doorway_leads_bruts.group_leads_bruts_user",
    "doorway_leads_bruts.group_leads_bruts_manager",
    "doorway_leads_bruts.group_admin_commercial",
    "doorway_credits.group_doorway_credits_admin",
    "doorway_social_ia.group_social_manager",
    "doorway_traffic_manager.group_traffic_manager",
    "doorway_veille_sociale.group_veille_settings",
    "doorway_messaging.group_messaging_user",
    "intellix_support.group_intellix_support_user",
)


class PeopleEngineProfile(models.Model):
    _name = "pe.employee.profile"
    _description = "Profil People Engine"
    _inherit = ["mail.thread", "mail.activity.mixin", "pe.variable.prime.mixin"]
    _rec_name = "display_name"
    _order = "score_global desc"

    employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="cascade", index=True
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)
    user_id = fields.Many2one(related="employee_id.user_id", store=True)
    department_id = fields.Many2one(
        related="employee_id.department_id", store=True, readonly=False
    )
    job_id = fields.Many2one(related="employee_id.job_id", store=True, readonly=False)
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, readonly=False
    )
    parent_id = fields.Many2one(
        related="employee_id.parent_id",
        store=True,
        readonly=False,
        string="Manager",
    )
    doorway_segment = fields.Selection(
        related="user_id.doorway_segment",
        store=True,
        readonly=True,
        string="Segment Doorway",
    )
    doorway_role = fields.Selection(
        related="user_id.doorway_role",
        store=True,
        readonly=True,
        string="Rôle Doorway",
    )
    doorway_assigned_pipeline_ids = fields.Many2many(
        related="user_id.doorway_assigned_pipeline_ids",
        readonly=False,
        string="Pipelines assignés",
        help="Pipelines CRM visibles pour ce collaborateur. "
        "Les onglets CRM et les droits leads sont synchronisés sur le compte utilisateur.",
    )
    doorway_permission_group_ids = fields.Many2many(
        "res.groups",
        string="Permissions Doorway",
        compute="_compute_doorway_permission_group_ids",
        inverse="_inverse_doorway_permission_group_ids",
        help="Applications et niveaux d'accès CRM Doorway / IntelliX. "
        "Le segment et le rôle affichés ci-dessus se mettent à jour automatiquement.",
    )
    vicidial_agent_id = fields.Char(
        string="Agent ID VICIdial",
        help="Ex: 1001 — détection présence et stats appels.",
    )
    vicidial_user = fields.Char(string="Login VICIdial")
    type_remuneration = fields.Selection(
        [
            ("salaire", "Salaire fixe mensuel"),
            ("honoraire", "Honoraires (freelance)"),
            ("mixte", "Fixe + variable"),
        ],
        default="mixte",
    )
    salaire_base = fields.Float(string="Salaire / honoraire base")
    montant_variable = fields.Float(
        string="Part variable (cible)",
        help="Montant variable cible ou estimé, dans la devise de rémunération.",
    )
    taux_commission = fields.Float(
        string="Taux variable (%)",
        help="Pourcentage de commission ou part variable sur objectifs.",
    )
    description_variable = fields.Text(
        string="Description du variable",
        help="Structure de commission, plafond, critères d'attribution…",
    )
    devise_remuneration = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("CAD", "CAD")],
        default="MAD",
    )
    regime_travail = fields.Selection(
        [
            ("temps_plein", "Temps plein"),
            ("mi_temps", "Mi-temps (50 %)"),
        ],
        string="Régime de travail",
        default="temps_plein",
    )
    coefficient_objectifs = fields.Float(
        string="Coefficient objectifs",
        default=1.0,
        help="1.0 = objectifs complets du département ; 0.5 = mi-temps.",
    )
    pays_affectation = fields.Selection(
        [
            ("MA", "Maroc"),
            ("CA", "Canada"),
            ("FR", "France"),
            ("QC", "Québec"),
        ],
        string="Pays d'affectation",
    )
    hors_paie_maroc = fields.Boolean(
        string="Hors paie Maroc",
        default=False,
        tracking=True,
        help="Exclut cet employé des bulletins de paie Maroc (période 25→24, CNSS, SMIG). "
        "À activer pour les salariés payés par une entité étrangère (ex. Canada).",
    )
    entite_paie_externe = fields.Char(
        string="Entité de paie externe",
        help="Société ou entité qui rémunère l'employé hors paie Maroc (ex. Agence Doorway Inc., Canada).",
    )
    agent_ia_personnel_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA prospecteur personnel",
    )
    department_pe_id = fields.Many2one(
        "pe.department", string="Département RH"
    )
    type_usager_pe = fields.Selection(
        [
            ("prospecteur_vicidial", "Prospecteur VICIdial"),
            ("prospecteur_social", "Prospecteur réseaux sociaux"),
            ("closeur", "Agent closeur"),
            ("gestionnaire", "Gestionnaire"),
            ("mixte", "Mixte"),
        ],
        string="Rôle dans le département",
        default="mixte",
    )
    pe_status = fields.Selection(
        [
            ("active", "Actif"),
            ("monitoring", "Surveillance"),
            ("coaching", "En coaching"),
            ("on_leave", "En congé"),
            ("inactive", "Inactif"),
        ],
        default="active",
        tracking=True,
    )
    lifecycle_stage_id = fields.Many2one(
        "pe.employee.lifecycle.stage",
        string="Stade cycle de vie",
        tracking=True,
        help="Détermine les documents proposés depuis la banque RH.",
    )
    lifecycle_stage_code = fields.Char(
        related="lifecycle_stage_id.code",
        string="Code stade",
    )
    document_ids = fields.One2many(
        "pe.employee.document",
        "profile_id",
        string="Documents envoyés",
    )
    contract_ids = fields.One2many(
        "pe.employment.contract",
        "profile_id",
        string="Contrats",
    )
    active_contract_id = fields.Many2one(
        "pe.employment.contract",
        compute="_compute_active_contract",
        string="Contrat actif",
    )
    contract_count = fields.Integer(compute="_compute_contract_count")
    pe_group_summary = fields.Char(
        compute="_compute_pe_group_summary",
        string="Groupes RH",
    )
    document_count = fields.Integer(compute="_compute_document_count")
    disciplinary_incident_count = fields.Integer(compute="_compute_disciplinary_counts")
    disciplinary_procedure_count = fields.Integer(compute="_compute_disciplinary_counts")
    current_score = fields.Float(
        related="score_global", string="Score actuel", store=True
    )
    score_performance = fields.Float(string="Performance /40", default=0.0)
    score_engagement = fields.Float(string="Engagement /30", default=0.0)
    score_growth = fields.Float(string="Croissance /30", default=0.0)
    objectives_achievement_pct = fields.Float(
        string="Taux objectifs (%)",
        help="Moyenne pondérée du taux d'atteinte des objectifs actifs.",
    )
    score_global = fields.Float(string="Score global /100", default=0.0, tracking=True)
    score_trend = fields.Selection(
        [
            ("up", "En hausse"),
            ("stable", "Stable"),
            ("down", "En baisse"),
        ],
        default="stable",
    )
    score_trend_percent = fields.Float(default=0.0)
    pe_avatar_initials = fields.Char(compute="_compute_pe_mockup_display")
    pe_score_ring_svg = fields.Html(compute="_compute_pe_mockup_display", sanitize=False)
    pe_score_trend_label = fields.Char(compute="_compute_pe_mockup_display")
    pe_hire_date_label = fields.Char(compute="_compute_pe_mockup_display")
    pe_ai_insight_text = fields.Text(compute="_compute_pe_mockup_display")
    pe_type_usager_label = fields.Char(compute="_compute_pe_mockup_display")
    pe_status_display = fields.Char(compute="_compute_pe_mockup_display")
    pe_avatar_gradient = fields.Char(compute="_compute_pe_team_list_display")
    pe_team_employee_cell = fields.Html(compute="_compute_pe_team_list_display", sanitize=False)
    pe_team_score_cell = fields.Html(compute="_compute_pe_team_list_display", sanitize=False)
    pe_team_period_score = fields.Float(compute="_compute_pe_team_list_display")

    last_score_update = fields.Datetime()
    alert_count = fields.Integer(compute="_compute_alert_count")
    performance_band = fields.Selection(
        [
            ("excellent", "Excellent (>80)"),
            ("good", "Bon (60-80)"),
            ("watch", "À surveiller (<60)"),
        ],
        compute="_compute_performance_band",
        store=True,
    )
    snapshot_ids = fields.One2many("pe.metric.snapshot", "profile_id")
    objective_ids = fields.One2many("pe.objective", "profile_id")
    signature_count = fields.Integer(compute="_compute_signature_count", string="Signatures")

    def _compute_signature_count(self):
        Sig = self.env["pe.electronic.signature"].sudo()
        for rec in self:
            try:
                rec.signature_count = Sig.search_count([("profile_id", "=", rec.id)])
            except Exception:
                rec.signature_count = 0

    def action_view_signatures(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Signatures électroniques",
            "res_model": "pe.electronic.signature",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
        }
    operational_objective_ids = fields.One2many(
        "pe.objective",
        "profile_id",
        domain=[("contract_id", "=", False)],
        string="Objectifs opérationnels",
    )
    visites_terrain_count = fields.Integer(
        string="Visites terrain",
        default=0,
        help="Nombre de visites terrain sur la période (saisie manuelle V1).",
    )
    demos_count = fields.Integer(
        string="Démos réalisées",
        default=0,
        help="Nombre de démos sur la période (saisie manuelle V1).",
    )
    evaluation_ids = fields.One2many("pe.evaluation", "profile_id")
    action_log_ids = fields.One2many("pe.action.log", "profile_id")
    score_history_ids = fields.One2many("pe.performance.score", "profile_id")
    coaching_session_ids = fields.One2many("pe.coaching.session", "profile_id")
    coaching_plan_ids = fields.One2many("pe.coaching.plan", "profile_id")
    badge_award_ids = fields.One2many("pe.badge.award", "profile_id")
    employee_level_id = fields.One2many(
        "pe.employee.level", "profile_id", string="Niveau PE"
    )
    badge_award_count = fields.Integer(compute="_compute_badge_award_count")
    pe_points_total = fields.Integer(compute="_compute_pe_points_total")
    pe_level_name = fields.Char(compute="_compute_pe_level_name")
    crm_leads_assigned = fields.Integer(default=0)
    crm_leads_won = fields.Integer(default=0)
    crm_conversion_rate = fields.Float(default=0.0)
    crm_avg_response_time = fields.Float(
        string="Temps moyen réponse (h)",
        help="Temps moyen de réponse aux leads (heures)",
        default=0.0,
    )
    crm_revenue_generated = fields.Float(default=0.0)
    project_tasks_assigned = fields.Integer(default=0)
    project_tasks_done = fields.Integer(default=0)
    project_tasks_ontime = fields.Integer(default=0)
    project_ontime_rate = fields.Float(default=0.0)
    project_avg_completion_days = fields.Float(default=0.0)
    ia_calls_made = fields.Integer(default=0)
    ia_avg_quality_score = fields.Float(default=0.0)
    ia_avg_call_duration = fields.Float(string="Durée moyenne appels (s)", default=0.0)
    ia_conversion_rate = fields.Float(default=0.0)
    activity_login_days = fields.Integer(default=0)
    activity_messages_sent = fields.Integer(default=0)
    activity_tasks_created = fields.Integer(default=0)
    metric_period_start = fields.Date()
    metric_period_end = fields.Date()
    metric_period_days = fields.Selection(
        [
            ("7", "7 jours"),
            ("30", "30 jours"),
            ("90", "90 jours"),
            ("custom", "Personnalisé"),
        ],
        default="30",
    )

    _employee_unique = models.Constraint(
        "unique(employee_id)",
        "Un seul profil People Engine par employé.",
    )

    @api.model
    def _doorway_manageable_permission_groups(self):
        groups = self.env["res.groups"]
        for xmlid in DOORWAY_PERMISSION_GROUP_XMLIDS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups |= group
        return groups

    @api.depends("user_id", "user_id.group_ids")
    def _compute_doorway_permission_group_ids(self):
        manageable = self._doorway_manageable_permission_groups()
        for rec in self:
            if rec.user_id:
                rec.doorway_permission_group_ids = rec.user_id.group_ids & manageable
            else:
                rec.doorway_permission_group_ids = False

    def _inverse_doorway_permission_group_ids(self):
        manageable = self._doorway_manageable_permission_groups()
        for rec in self:
            user = rec.user_id.sudo()
            if not user:
                continue
            current = user.group_ids & manageable
            target = rec.doorway_permission_group_ids
            commands = [(4, g.id) for g in target - current]
            commands += [(3, g.id) for g in current - target]
            if commands:
                user.with_context(skip_pe_group_resync=True).write(
                    {"group_ids": commands}
                )

    def _check_doorway_access_write(self):
        if self.env.user.has_group("people_engine.group_hr") or self.env.user.has_group(
            "people_engine.group_manager"
        ) or self.env.user.has_group("base.group_system"):
            return
        raise AccessError(
            _(
                "Seuls la RH et les gestionnaires peuvent modifier les pipelines "
                "et permissions Doorway."
            )
        )

    @api.depends(
        "employee_id",
        "employee_id.name",
        "score_global",
        "score_trend",
        "score_trend_percent",
        "pe_status",
        "type_usager_pe",
        "lifecycle_stage_id",
        "lifecycle_stage_id.name",
        "department_id",
        "parent_id",
        "objectives_achievement_pct",
    )
    def _compute_pe_mockup_display(self):
        type_labels = dict(self._fields["type_usager_pe"].selection)
        status_labels = dict(self._fields["pe_status"].selection)
        trend_labels = {
            "up": "↑ En hausse",
            "down": "↓ En baisse",
            "stable": "↔ Stable",
        }
        for rec in self:
            name = rec.employee_id.name or ""
            parts = [p for p in name.split() if p]
            if len(parts) >= 2:
                initials = (parts[0][0] + parts[-1][0]).upper()
            elif parts:
                initials = parts[0][:2].upper()
            else:
                initials = "?"
            rec.pe_avatar_initials = initials
            pct = max(0.0, min(100.0, rec.score_global or 0.0))
            circumference = 213.6
            offset = circumference - (circumference * pct / 100.0)
            score_int = int(round(pct))
            rec.pe_score_ring_svg = (
                '<div class="pe-emp-score-ring-wrap">'
                '<svg width="80" height="80" viewBox="0 0 80 80" aria-hidden="true">'
                '<circle cx="40" cy="40" r="34" fill="none" '
                'stroke="rgba(255,255,255,0.06)" stroke-width="6"/>'
                '<circle cx="40" cy="40" r="34" fill="none" '
                'stroke="url(#peScoreGradMock)" stroke-width="6" '
                f'stroke-dasharray="{circumference}" stroke-dashoffset="{offset:.2f}" '
                'stroke-linecap="round" transform="rotate(-90 40 40)"/>'
                '<defs><linearGradient id="peScoreGradMock" x1="0%" y1="0%" x2="100%" y2="0%">'
                '<stop offset="0%" stop-color="#6366f1"/>'
                '<stop offset="100%" stop-color="#8b5cf6"/>'
                '</linearGradient></defs></svg>'
                f'<div class="pe-emp-score-ring-center">'
                f'<span class="pe-emp-score-ring-val">{score_int}</span>'
                f'<span class="pe-emp-score-ring-max">/100</span></div></div>'
            )
            rec.pe_score_trend_label = trend_labels.get(
                rec.score_trend or "stable", "↔ Stable"
            )
            if rec.score_trend == "down" and rec.score_trend_percent:
                rec.pe_score_trend_label = (
                    f"↓ En baisse ({rec.score_trend_percent:.0f}%)"
                )
            elif rec.score_trend == "up" and rec.score_trend_percent:
                rec.pe_score_trend_label = (
                    f"↑ En hausse (+{rec.score_trend_percent:.0f}%)"
                )
            hire = rec.employee_id.create_date
            if hire:
                from odoo.tools.misc import format_date
                rec.pe_hire_date_label = _("Depuis le %s") % format_date(
                    rec.env, hire.date()
                )
            else:
                rec.pe_hire_date_label = ""
            rec.pe_type_usager_label = type_labels.get(rec.type_usager_pe, "")
            rec.pe_status_display = status_labels.get(rec.pe_status, "")
            stage = rec.lifecycle_stage_id.name or ""
            score = int(rec.score_global or 0)
            first = name.split()[0] if name else _("Collaborateur")
            if score < 40:
                rec.pe_ai_insight_text = _(
                    "%(name)s est en %(stage)s. Son score est à %(score)s/100 — "
                    "recommandation : vérifier les métriques VICIdial/CRM et relancer le calcul."
                ) % {
                    "name": first,
                    "stage": stage or _("intégration"),
                    "score": score,
                }
            elif score < 60:
                rec.pe_ai_insight_text = _(
                    "Score %(score)s/100 — surveillance recommandée. "
                    "Planifier un point coaching IA cette semaine."
                ) % {"score": score}
            else:
                rec.pe_ai_insight_text = _(
                    "Performance solide (%(score)s/100). "
                    "Envisager une félicitation ou un défi prime."
                ) % {"score": score}

    @api.depends("employee_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.employee_id.name or _("Profil People Engine")

    def _action_company_context(self, action):
        self.ensure_one()
        company_id = self.sudo().company_id.id
        if not company_id:
            return action
        ctx = dict(action.get("context") or {})
        raw_cids = ctx.get("allowed_company_ids") or self.env.companies.ids
        cids = [c[0] if isinstance(c, (list, tuple)) else c for c in raw_cids]
        if company_id not in cids:
            cids.append(company_id)
        ctx["allowed_company_ids"] = cids
        action["context"] = ctx
        return action

    @api.model
    def _pe_action_context(self, extra=None):
        """Élargit le contexte sociétés pour les profils multi-organisation."""
        ctx = dict(extra or {})
        cids = set(self.env.user.company_ids.ids) | set(self.env.companies.ids)
        if self.env.user.has_group("people_engine.group_hr") or self.env.user.has_group(
            "base.group_system"
        ):
            cids |= set(
                self.sudo().search([]).mapped("company_id").ids
            )
        ctx["allowed_company_ids"] = list(cids)
        return ctx

    def _with_pe_company_access(self):
        cids = set(self.env.user.company_ids.ids) | set(self.env.companies.ids)
        cids |= set(self.sudo().mapped("company_id").ids)
        return self.with_context(allowed_company_ids=list(cids))

    def read(self, fields=None, load="_classic_read"):
        if self.env.user.has_group("people_engine.group_employee") or self.env.user.has_group(
            "base.group_system"
        ) or self.env.user.has_group("hr.group_hr_user"):
            return super(
                PeopleEngineProfile, self._with_pe_company_access()
            ).read(fields, load)
        return super().read(fields, load)

    def web_read(self, specification):
        if self.env.user.has_group("people_engine.group_employee") or self.env.user.has_group(
            "base.group_system"
        ) or self.env.user.has_group("hr.group_hr_user"):
            return super(
                PeopleEngineProfile, self._with_pe_company_access()
            ).web_read(specification)
        return super().web_read(specification)

    def get_formview_action(self, access_uid=None):
        action = super().get_formview_action(access_uid=access_uid)
        return self._action_company_context(action)

    def action_open_hr_employee(self):
        """Fiche technique hr.employee — réservée au super admin Odoo."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            return False
        return self.employee_id.with_context(
            force_hr_employee_form=True
        )._action_company_context(
            {
                "type": "ir.actions.act_window",
                "name": self.employee_id.name,
                "res_model": "hr.employee",
                "res_id": self.employee_id.id,
                "view_mode": "form",
                "target": "current",
            }
        )

    def action_send_invitation(self):
        self.ensure_one()
        user = self.user_id
        if not user:
            from odoo.exceptions import UserError

            raise UserError(_("Aucun utilisateur lié à ce profil."))
        return user.action_reset_password()

    def action_open_user_permissions(self):
        self.ensure_one()
        user = self.user_id
        if not user:
            from odoo.exceptions import UserError

            raise UserError(_("Aucun utilisateur lié à ce profil."))
        action = {
            "type": "ir.actions.act_window",
            "name": _("Accès — %s") % user.name,
            "res_model": "res.users",
            "res_id": user.id,
            "view_mode": "form",
            "target": "current",
            "views": [
                (self.env.ref("people_engine.view_pe_user_access_form").id, "form")
            ],
        }
        return self._action_company_context(action)


    PE_TEAM_AVATAR_GRADIENTS = (
        "linear-gradient(135deg,#6366f1,#8b5cf6)",
        "linear-gradient(135deg,#f59e0b,#fb923c)",
        "linear-gradient(135deg,#10b981,#06b6d4)",
        "linear-gradient(135deg,#8b5cf6,#a855f7)",
        "linear-gradient(135deg,#ec4899,#f43f5e)",
        "linear-gradient(135deg,#f59e0b,#fbbf24)",
        "linear-gradient(135deg,#6366f1,#06b6d4)",
    )

    @api.model
    def _pe_team_period_days(self):
        days = self.env.context.get("pe_team_period_days", 30)
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 30
        return days if days in (7, 30, 90) else 30

    @api.model
    def _pe_team_avatar_style(self, profile):
        if profile.pe_status == "inactive":
            return "background:#1a1a2e;border:1px solid rgba(255,255,255,0.1)"
        gradient = profile.pe_avatar_gradient or self.PE_TEAM_AVATAR_GRADIENTS[0]
        return f"background:{gradient}"

    @api.model
    def _pe_team_score_colors(self, score):
        if score >= 80:
            return "#10b981", "#34d399"
        if score >= 60:
            return "#6366f1", "#818cf8"
        if score >= 40:
            return "#f59e0b", "#fbbf24"
        return "#ef4444", "#f87171"

    def _get_profile_period_score(self, period_days=None):
        self.ensure_one()
        period_days = period_days or self._pe_team_period_days()
        today = fields.Date.context_today(self)
        start = today - timedelta(days=period_days)
        score_rec = self.env["pe.performance.score"].sudo().search(
            [
                ("profile_id", "=", self.id),
                ("period_end", ">=", start),
                ("period_end", "<=", today),
            ],
            order="period_end desc",
            limit=1,
        )
        if score_rec:
            return score_rec.score_global
        return self.score_global or 0.0

    @api.depends(
        "employee_id",
        "employee_id.name",
        "job_id",
        "job_id.name",
        "pe_status",
        "score_global",
        "pe_avatar_initials",
    )
    def _compute_pe_team_list_display(self):
        period_days = self._pe_team_period_days()
        for rec in self:
            rec_id = rec.id or 0
            rec.pe_avatar_gradient = self.PE_TEAM_AVATAR_GRADIENTS[
                rec_id % len(self.PE_TEAM_AVATAR_GRADIENTS)
            ]
            period_score = rec._get_profile_period_score(period_days)
            rec.pe_team_period_score = period_score
            avatar_style = self._pe_team_avatar_style(rec)
            role = rec.job_id.name or ""
            initials = rec.pe_avatar_initials or "?"
            rec.pe_team_employee_cell = (
                "<div class=\"pe-team-emp-cell\">"
                f"<div class=\"pe-team-mini-avatar\" style=\"{avatar_style}\">{initials}</div>"
                "<div>"
                f"<div class=\"pe-team-emp-name\">{rec.display_name or ""}</div>"
                f"<div class=\"pe-team-emp-role\">{role}</div>"
                "</div></div>"
            )
            bar_color, num_color = self._pe_team_score_colors(period_score)
            pct = max(0, min(100, int(round(period_score))))
            score_int = int(round(period_score))
            rec.pe_team_score_cell = (
                "<div class=\"pe-team-score-cell\">"
                "<div class=\"pe-team-score-mini-bar\">"
                f"<div class=\"pe-team-score-mini-fill\" style=\"width:{pct}%;background:{bar_color}\"></div>"
                "</div>"
                f"<span class=\"pe-team-score-num\" style=\"color:{num_color}\">{score_int}</span>"
                "</div>"
            )

    @api.model
    def _resolve_profile_employee_id(self, explicit_id=None):
        """Résout employee_id pour création / défauts (multi-société)."""
        if explicit_id:
            return explicit_id
        ctx_id = self.env.context.get("default_employee_id")
        if ctx_id:
            return ctx_id
        employee = self.env["hr.employee"].pe_resolve_user_employee()
        return employee.id if employee else False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "employee_id" in fields_list and not res.get("employee_id"):
            employee_id = self._resolve_profile_employee_id()
            if employee_id:
                res["employee_id"] = employee_id
        return res

    def _get_team_domain(self):
        """Domaine profils visibles pour le tableau de bord équipe."""
        employee = self.env["hr.employee"].pe_resolve_user_employee()
        if self.env.user.has_group("people_engine.group_hr") or self.env.user.has_group(
            "base.group_system"
        ):
            return []
        if self.env.user.has_group("people_engine.group_manager") and employee:
            return [
                "|",
                ("employee_id.parent_id", "=", employee.id),
                ("employee_id", "=", employee.id),
            ]
        if employee:
            return [("employee_id.user_id", "=", self.env.uid)]
        return [("id", "=", 0)]

    @api.model
    def action_export_team_dashboard_csv(self, period_days=30):
        """Export CSV équipe — dashboard manager."""
        import base64
        import csv
        import io

        data = self.get_team_dashboard_data(period_days=period_days)
        profiles = self.search(self._get_team_domain())
        period_scores = {
            p.id: p.with_context(pe_team_period_days=period_days)._get_profile_period_score(period_days)
            for p in profiles
        }
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow([
            "Employé", "Statut PE", "Score période", "Score global",
            "Qualification %", "Département",
        ])
        for profile in profiles.sorted(key=lambda p: period_scores.get(p.id, 0), reverse=True):
            writer.writerow([
                profile.display_name,
                profile.pe_status or "",
                period_scores.get(profile.id, 0),
                profile.score_global or 0,
                profile.objectives_achievement_pct or profile.ia_avg_quality_score or 0,
                profile.department_id.name or "",
            ])
        content = buf.getvalue().encode("utf-8-sig")
        att = self.env["ir.attachment"].sudo().create({
            "name": "equipe_rh_%sd.csv" % data.get("period_label", "30j"),
            "type": "binary",
            "datas": base64.b64encode(content),
            "mimetype": "text/csv",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % att.id,
            "target": "self",
        }

    @api.model
    def get_team_dashboard_data(self, period_days=30):
        """KPIs + panneaux latéraux — maquette Vue Équipe RH."""
        try:
            period_days = int(period_days)
        except (TypeError, ValueError):
            period_days = 30
        if period_days not in (7, 30, 90):
            period_days = 30
        period_label = f"{period_days}j"
        chart_labels = {7: _("7 derniers jours"), 30: _("30 derniers jours"), 90: _("90 derniers jours")}
        today = fields.Date.context_today(self)
        profiles = self.search(self._get_team_domain())
        total = len(profiles)
        period_scores = {
            p.id: p.with_context(pe_team_period_days=period_days)._get_profile_period_score(period_days)
            for p in profiles
        }
        avg_score = (
            round(sum(period_scores.values()) / total, 1) if total else 0.0
        )
        monitoring = profiles.filtered(lambda p: p.pe_status == "monitoring")
        monitoring_count = len(monitoring)
        qual_rates = [
            p.objectives_achievement_pct or p.ia_avg_quality_score or 0.0
            for p in profiles
        ]
        avg_qual = round(sum(qual_rates) / total, 1) if total else 0.0
        probation = profiles.filtered(
            lambda p: p.lifecycle_stage_code == "probation"
        )
        inactive = profiles.filtered(lambda p: p.pe_status == "inactive")
        onboarding_profiles = profiles.filtered(
            lambda p: p.lifecycle_stage_code in ("arrival", "probation", "onboarding")
            or p.pe_status in ("monitoring", "coaching")
        )[:3]

        period_start = today - timedelta(days=period_days)
        month_label = period_label
        Prime = self.env["pe.prime"].sudo()
        primes = Prime.search(
            [
                ("status", "in", ["pending_manager", "pending_hr", "pending_dg"]),
                ("period_start", ">=", period_start),
            ],
            limit=5,
        )
        primes_pending = Prime.search_count(
            [
                ("status", "in", ["pending_manager", "pending_hr", "pending_dg"]),
                ("period_start", ">=", period_start),
            ]
        )
        onboarding_count = len(
            profiles.filtered(
                lambda p: p.lifecycle_stage_code in ("arrival", "probation", "onboarding")
            )
        )

        today = fields.Date.context_today(self)
        prev_start = today - timedelta(days=period_days * 2)
        prev_end = today - timedelta(days=period_days)
        prev_scores = self.env["pe.performance.score"].sudo().search(
            [
                ("profile_id", "in", profiles.ids),
                ("period_end", ">=", prev_start),
                ("period_end", "<", prev_end),
            ]
        )
        prev_avg = (
            round(sum(prev_scores.mapped("score_global")) / len(prev_scores), 1)
            if prev_scores
            else avg_score
        )

        kpis = {
            "total_employees": total,
            "total_trend": _("↑ actifs") if total else "—",
            "avg_score": avg_score,
            "avg_score_trend": _("↓ -%(pts)s pts") % {"pts": max(0, round(prev_avg - avg_score))}
            if prev_avg > avg_score
            else _("↑ +%(pts)s pts") % {"pts": max(0, round(avg_score - prev_avg))}
            if avg_score > prev_avg
            else _("— Stable"),
            "avg_score_trend_class": "pe-team-trend-down"
            if prev_avg > avg_score
            else "pe-team-trend-up"
            if avg_score > prev_avg
            else "pe-team-trend-neutral",
            "monitoring_count": monitoring_count,
            "monitoring_trend": _("— Stable"),
            "monitoring_pct": min(100, round(100 * monitoring_count / total)) if total else 0,
            "avg_qual_rate": avg_qual,
            "avg_qual_trend": _("↑ données PE") if avg_qual else "—",
            "primes_pending": primes_pending,
            "primes_period": month_label,
            "primes_pct": min(100, round(100 * primes_pending / max(total, 1))),
            "onboarding_count": onboarding_count or len(onboarding_profiles),
            "onboarding_pct": min(
                100, round(100 * (onboarding_count or len(onboarding_profiles)) / max(total, 1))
            ),
        }

        leaderboard = []
        sorted_profiles = sorted(
            profiles,
            key=lambda p: period_scores.get(p.id, p.score_global or 0),
            reverse=True,
        )[:5]
        for rank, profile in enumerate(sorted_profiles, start=1):
            pscore = period_scores.get(profile.id, profile.score_global or 0)
            badge = ""
            if pscore >= 80:
                badge = "🥇"
            elif pscore >= 70:
                badge = "🥈"
            _bar_color, score_color = self._pe_team_score_colors(pscore)
            leaderboard.append(
                {
                    "rank": rank,
                    "profile_id": profile.id,
                    "name": profile.display_name,
                    "initials": profile.pe_avatar_initials or "?",
                    "avatar_style": self._pe_team_avatar_style(profile),
                    "score": int(round(pscore)),
                    "score_color": score_color,
                    "badge": badge,
                }
            )

        alerts = self._build_team_dashboard_alerts(profiles, monitoring, probation)
        status_distrib = self._build_team_status_distrib(profiles, total)
        onboarding_pipeline = self._build_team_onboarding_pipeline(onboarding_profiles)
        primes_due = self._build_team_primes_due(primes, profiles)
        score_chart = self._build_team_score_chart(profiles, period_days=period_days)

        return {
            "kpis": kpis,
            "leaderboard": leaderboard,
            "alerts": alerts,
            "status_distrib": status_distrib,
            "onboarding_pipeline": onboarding_pipeline,
            "primes_due": primes_due,
            "score_chart": score_chart,
            "period_days": period_days,
            "period_label": period_label,
            "chart_label": chart_labels.get(period_days, period_label),
            "filter_counts": {
                "all": total,
                "monitoring": monitoring_count,
                "probation": len(probation),
                "inactive": len(inactive),
            },
        }

    @api.model
    def get_team_kanban_employees(self):
        """Employés kanban 3 colonnes — scores et alertes pour dashboard équipe."""
        profiles = self.search(self._get_team_domain())
        Alert = self.env["pe.supervisor.alert"].sudo()
        rows = []
        for profile in profiles:
            emp = profile.employee_id
            if not emp:
                continue
            score = profile.score_global or 0.0
            if score < 60:
                band = "watch"
            elif score < 80:
                band = "growing"
            else:
                band = "top"
            rows.append(
                {
                    "id": emp.id,
                    "name": emp.name,
                    "job_title": emp.job_title or (profile.job_id.name if profile.job_id else ""),
                    "people_score": score,
                    "people_score_trend": profile.score_trend or "stable",
                    "people_alerts_count": Alert.search_count(
                        [("employee_id", "=", emp.id), ("state", "=", "active")]
                    ),
                    "people_band": band,
                    "pe_profile_id": profile.id,
                }
            )
        return rows

    @api.model
    def _build_team_dashboard_alerts(self, profiles, monitoring, probation):
        alerts = []
        critical = profiles.filtered(lambda p: p.score_global < 40)[:1]
        if critical:
            p = critical[0]
            alerts.append(
                {
                    "type": "danger",
                    "icon": "⚠",
                    "title": _("Score critique — %s") % p.display_name,
                    "text": _("Score global %(score)s/100 — coaching urgent.") % {
                        "score": int(p.score_global)
                    },
                    "profile_id": p.id,
                }
            )
        if monitoring:
            p = monitoring[0]
            alerts.append(
                {
                    "type": "warn",
                    "icon": "👁",
                    "title": _("Surveillance — %s") % p.display_name,
                    "text": _("Performance sous seuil — plan d'action recommandé."),
                    "profile_id": p.id,
                }
            )
        if probation:
            alerts.append(
                {
                    "type": "info",
                    "icon": "📋",
                    "title": _("%(n)s périodes d'essai actives") % {"n": len(probation)},
                    "text": _("Suivi fin d'essai et documents RH à valider."),
                    "profile_id": probation[0].id if probation else False,
                }
            )
        return alerts[:3]

    @api.model
    def _build_team_status_distrib(self, profiles, total):
        mapping = [
            ("active", "● Actif", "#10b981"),
            ("monitoring", "● Surveillance", "#f59e0b"),
            ("coaching", "● Coaching", "#818cf8"),
            ("on_leave", "● Congé", "#06b6d4"),
            ("inactive", "● Inactif", "#ef4444"),
        ]
        rows = []
        for key, label, color in mapping:
            count = len(profiles.filtered(lambda p: p.pe_status == key))
            if not count and key not in ("active", "monitoring", "inactive"):
                continue
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "color": color,
                    "count": count,
                    "pct": round(100 * count / total) if total else 0,
                }
            )
        return rows

    @api.model
    def _build_team_onboarding_pipeline(self, profiles):
        if not profiles:
            return []
        pipelines = []
        for profile in profiles[:2]:
            stage = profile.lifecycle_stage_id.name or _("Onboarding")
            pipelines.append(
                {
                    "employee": profile.display_name,
                    "steps": [
                        {"num": "✓", "label": _("Profil créé"), "state": "done"},
                        {
                            "num": "2",
                            "label": stage,
                            "state": "active",
                        },
                        {"num": "3", "label": _("Contrat / documents"), "state": "pending"},
                        {"num": "4", "label": _("Formation Academy"), "state": "pending"},
                    ],
                }
            )
        return pipelines

    @api.model
    def _build_team_primes_due(self, primes, profiles):
        rows = []
        for prime in primes:
            profile = prime.profile_id
            tier = "Gold 🥇" if profile.score_global >= 80 else "Silver 🥈"
            rows.append(
                {
                    "initials": profile.pe_avatar_initials or "?",
                    "avatar_style": self._pe_team_avatar_style(profile),
                    "name": profile.display_name,
                    "meta": _("Score %(score)s · %(tier)s")
                    % {"score": int(profile.score_global), "tier": tier},
                    "amount_label": "+20%" if profile.score_global >= 80 else "+10%",
                }
            )
        if not rows and profiles:
            for profile in profiles.sorted(key=lambda p: p.score_global, reverse=True)[:3]:
                rows.append(
                    {
                        "initials": profile.pe_avatar_initials or "?",
                        "avatar_style": self._pe_team_avatar_style(profile),
                        "name": profile.display_name,
                        "meta": _("Score %(score)s · Palier variable")
                        % {"score": int(profile.score_global)},
                        "amount_label": "+15%",
                    }
                )
        return rows[:3]

    @api.model
    def _build_team_score_chart(self, profiles, period_days=30):
        Score = self.env["pe.performance.score"].sudo()
        points = []
        today = fields.Date.context_today(self)
        bucket_count = 6
        bucket_days = max(1, period_days // bucket_count)
        buckets = []
        for i in range(bucket_count):
            end = today - timedelta(days=i * bucket_days)
            start = today - timedelta(days=(i + 1) * bucket_days - 1)
            buckets.insert(0, (start, end))
        for idx, (start, end) in enumerate(buckets):
            scores = Score.search(
                [
                    ("profile_id", "in", profiles.ids),
                    ("period_end", ">=", start),
                    ("period_end", "<=", end),
                ]
            )
            if scores:
                value = round(sum(scores.mapped("score_global")) / len(scores), 1)
            elif profiles:
                ctx_scores = [
                    p.with_context(pe_team_period_days=period_days)._get_profile_period_score(period_days)
                    for p in profiles
                ]
                value = round(sum(ctx_scores) / len(ctx_scores), 1)
            else:
                value = 0
            if period_days <= 7:
                label = end.strftime("%d/%m")
            elif period_days <= 30:
                label = end.strftime("%d/%m")
            else:
                label = end.strftime("%b")
            points.append(
                {
                    "label": label,
                    "value": value,
                    "pct": min(100, int(value)),
                    "color": "#6366f1" if idx == len(buckets) - 1 else "#4f46e5",
                }
            )
        if not profiles:
            points = [
                {"label": "Jan", "value": 52, "pct": 52, "color": "#4f46e5"},
                {"label": "Fév", "value": 55, "pct": 55, "color": "#4f46e5"},
                {"label": "Mar", "value": 58, "pct": 58, "color": "#4f46e5"},
                {"label": "Avr", "value": 56, "pct": 56, "color": "#4f46e5"},
                {"label": "Mai", "value": 60, "pct": 60, "color": "#4f46e5"},
                {"label": "Juin", "value": 58, "pct": 58, "color": "#6366f1"},
            ]
        return points

    @api.model
    def action_open_team_profiles(self):
        """Vue Équipe — tableau de bord RH (maquette)."""
        team_list = self.env.ref(
            "people_engine.view_pe_employee_profile_team_list",
            raise_if_not_found=False,
        )
        action = {
            "type": "ir.actions.act_window",
            "name": _("Équipe"),
            "res_model": "pe.employee.profile",
            "view_mode": "list,kanban,form",
            "search_view_id": self.env.ref(
                "people_engine.view_pe_employee_profile_search"
            ).id,
            "context": self._pe_action_context({
                "form_view_ref": "people_engine.view_pe_employee_profile_form_mockup",
                "pe_team_period_days": 30,
            }),
        }
        if team_list:
            action["views"] = [
                (team_list.id, "list"),
                (False, "kanban"),
                (False, "form"),
            ]
        return action

    @api.model
    def action_open_hr_dashboard(self):
        action = {
            "type": "ir.actions.act_window",
            "name": _("Vue RH"),
            "res_model": "pe.employee.profile",
            "view_mode": "list,kanban,graph,pivot,form",
            "search_view_id": self.env.ref(
                "people_engine.view_pe_employee_profile_search"
            ).id,
            "context": self._pe_action_context(
                {"search_default_group_dept": 1}
            ),
        }
        return action

    @api.depends("score_global")
    def _compute_performance_band(self):
        for rec in self:
            if rec.score_global > 80:
                rec.performance_band = "excellent"
            elif rec.score_global >= 60:
                rec.performance_band = "good"
            else:
                rec.performance_band = "watch"

    def _compute_badge_award_count(self):
        data = self.env["pe.badge.award"].read_group(
            [("profile_id", "in", self.ids)], ["profile_id"], ["profile_id"]
        )
        counts = {row["profile_id"][0]: row["profile_id_count"] for row in data}
        for rec in self:
            rec.badge_award_count = counts.get(rec.id, 0)

    def _compute_pe_points_total(self):
        for rec in self:
            level = rec.employee_level_id[:1]
            rec.pe_points_total = level.total_points if level else 0

    def _compute_pe_level_name(self):
        for rec in self:
            level = rec.employee_level_id[:1]
            rec.pe_level_name = level.level_id.name if level and level.level_id else ""

    def _compute_document_count(self):
        data = self.env["pe.employee.document"].read_group(
            [("profile_id", "in", self.ids)],
            ["profile_id"],
            ["profile_id"],
        )
        counts = {row["profile_id"][0]: row["profile_id_count"] for row in data}
        for rec in self:
            rec.document_count = counts.get(rec.id, 0)

    @api.depends("contract_ids", "contract_ids.statut")
    def _compute_active_contract(self):
        for rec in self:
            active = rec.contract_ids.filtered(lambda c: c.statut == "active")[:1]
            rec.active_contract_id = active.id if active else False

    def _compute_contract_count(self):
        data = self.env["pe.employment.contract"].read_group(
            [("profile_id", "in", self.ids)],
            ["profile_id"],
            ["profile_id"],
        )
        counts = {row["profile_id"][0]: row["profile_id_count"] for row in data}
        for rec in self:
            rec.contract_count = counts.get(rec.id, 0)

    def _format_objectives_for_contract(self):
        """Synthèse textuelle des objectifs profil pour préremplir un contrat."""
        self.ensure_one()
        if not self.objective_ids:
            return False
        lines = ["<ul>"]
        for obj in self.objective_ids:
            target = ""
            if obj.target_value:
                unit = obj.unit or ""
                target = " — cible : %s%s" % (obj.target_value, unit)
            lines.append("<li><strong>%s</strong>%s</li>" % (obj.name, target))
            if obj.description:
                lines.append("<li><em>%s</em></li>" % obj.description)
        lines.append("</ul>")
        return "".join(lines)

    def _contract_create_vals(self, **extra):
        self.ensure_one()
        vals = {
            "employee_id": self.employee_id.id,
            "date_start": fields.Date.context_today(self),
            "salaire_base": self.salaire_base,
            "montant_variable": self.montant_variable,
            "taux_commission": self.taux_commission,
            "description_variable": self.description_variable,
            "variable_prime_template_id": self.variable_prime_template_id.id,
            "variable_prime_customize": self.variable_prime_customize,
            "devise": self.devise_remuneration or "MAD",
            "statut": "draft",
        }
        vals.update(extra)
        if not vals.get("objectifs_text"):
            objectifs = self._format_objectives_for_contract()
            if objectifs:
                vals["objectifs_text"] = objectifs
        if not vals.get("description_poste") and (self.job_id or self.department_id):
            parts = []
            if self.job_id:
                parts.append("<p><strong>Poste :</strong> %s</p>" % self.job_id.name)
            if self.department_id:
                parts.append(
                    "<p><strong>Département :</strong> %s</p>"
                    % self.department_id.name
                )
            vals["description_poste"] = "".join(parts)
        return vals

    @api.depends("user_id", "user_id.group_ids")
    def _compute_pe_group_summary(self):
        pe_privilege = self.env.ref(
            "people_engine.res_groups_privilege_people_engine",
            raise_if_not_found=False,
        )
        for rec in self:
            if not rec.user_id:
                rec.pe_group_summary = ""
                continue
            groups = rec.user_id.group_ids
            if pe_privilege:
                groups = groups.filtered(
                    lambda g: g.privilege_id.id == pe_privilege.id
                )
            else:
                groups = groups.filtered(lambda g: "RH" in (g.name or ""))
            rec.pe_group_summary = ", ".join(groups.mapped("name")) or _("Aucun")

    def _compute_disciplinary_counts(self):
        Incident = self.env["pe.disciplinary.incident"].sudo()
        Procedure = self.env["pe.disciplinary.procedure"].sudo()
        for rec in self:
            emp_id = rec.employee_id.id
            rec.disciplinary_incident_count = Incident.search_count(
                [("employee_id", "=", emp_id)]
            ) if emp_id else 0
            rec.disciplinary_procedure_count = Procedure.search_count(
                [("employee_id", "=", emp_id)]
            ) if emp_id else 0

    def action_view_disciplinary_dossier(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dossier disciplinaire — %s") % self.display_name,
            "res_model": "pe.disciplinary.incident",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.employee_id.id)],
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_superviseur_id": self.parent_id.id if self.parent_id else False,
            },
        }

    def _default_lifecycle_stage(self):
        return self.env.ref(
            "people_engine.lifecycle_stage_active",
            raise_if_not_found=False,
        )

    @api.model
    def action_open_my_profile(self, form_view_ref=None):
        """Ouvre le profil PE de l'utilisateur courant (crée si absent)."""
        employee = self.env["hr.employee"].pe_resolve_user_employee()
        if not employee:
            raise UserError(
                _(
                    "Aucune fiche employé RH n'est liée à votre compte. "
                    "Contactez les RH pour associer votre utilisateur."
                )
            )
        profile = self.sudo().search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if not profile:
            profile = self.create({"employee_id": employee.id})
        action = profile.get_formview_action()
        ctx = self._pe_action_context(
            {
                "form_view_ref": form_view_ref
                or "people_engine.view_dashboard_employee_form",
            }
        )
        base_ctx = action.get("context") or {}
        if not isinstance(base_ctx, dict):
            base_ctx = {}
        base_ctx.update(ctx)
        action["context"] = base_ctx
        return action

    @api.model_create_multi
    def create(self, vals_list):
        default_stage = self._default_lifecycle_stage()
        for vals in vals_list:
            if not vals.get("employee_id"):
                employee_id = self._resolve_profile_employee_id()
                if employee_id:
                    vals["employee_id"] = employee_id
            if not vals.get("employee_id"):
                raise UserError(
                    _(
                        "Sélectionnez un employé pour créer le profil RH, "
                        "ou associez une fiche hr.employee à votre compte."
                    )
                )
            existing = self.search(
                [("employee_id", "=", vals["employee_id"])], limit=1
            )
            if existing:
                raise UserError(
                    _(
                        "Un profil existe déjà pour cet employé (%s). "
                        "Ouvrez-le depuis RH › Équipe › Profils."
                    )
                    % (existing.display_name,)
                )
            if default_stage and not vals.get("lifecycle_stage_id"):
                vals["lifecycle_stage_id"] = default_stage.id
        profiles = super().create(vals_list)
        profiles.mapped("user_id").sync_pe_groups_from_profile()
        return profiles

    def write(self, vals):
        doorway_vals = {
            "doorway_assigned_pipeline_ids",
            "doorway_permission_group_ids",
        }
        if doorway_vals & set(vals):
            self._check_doorway_access_write()
        res = super().write(vals)
        if "type_usager_pe" in vals:
            self.mapped("user_id").sync_pe_groups_from_profile()
        return res

    def _action_personalize_document_window(self, *, arrival_pack=False, title=None):
        self.ensure_one()
        if arrival_pack:
            arrival = self.env.ref(
                "people_engine.lifecycle_stage_arrival",
                raise_if_not_found=False,
            )
            if arrival and self.lifecycle_stage_id != arrival:
                self.lifecycle_stage_id = arrival
        return {
            "type": "ir.actions.act_window",
            "name": title or _("Document personnalisé"),
            "res_model": "pe.personalize.document.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_profile_id": self.id,
                "default_arrival_pack": arrival_pack,
            },
        }

    def action_personalize_document(self):
        self.ensure_one()
        return self._action_personalize_document_window()

    def action_send_document(self):
        self.ensure_one()
        return self._action_personalize_document_window()

    def action_send_arrival_pack(self):
        self.ensure_one()
        return self._action_personalize_document_window(
            arrival_pack=True,
            title=_("Pack documents d'arrivée"),
        )

    def action_view_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Documents — %s") % self.display_name,
            "res_model": "pe.employee.document",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
        }

    def action_view_contracts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Contrats — %s") % self.display_name,
            "res_model": "pe.employment.contract",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_profile_id": self.id,
            },
        }

    def action_apply_objective_template(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Appliquer modèle d'objectifs"),
            "res_model": "pe.apply.objective.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_profile_id": self.id,
                "default_target": "profile",
            },
        }

    def action_save_objectives_as_template(self):
        self.ensure_one()
        objectives = self.operational_objective_ids
        if not objectives:
            from odoo.exceptions import UserError

            raise UserError(
                _("Aucun objectif opérationnel à enregistrer.")
            )
        return objectives.action_save_as_template()

    def _contract_form_action(self, contract, *, title=None):
        self.ensure_one()
        return self._action_company_context(
            {
                "type": "ir.actions.act_window",
                "name": title or contract.name,
                "res_model": "pe.employment.contract",
                "res_id": contract.id,
                "view_mode": "form",
                "target": "current",
            }
        )

    def action_create_contract(self):
        self.ensure_one()
        if not self.env.user.has_group("people_engine.group_hr"):
            from odoo.exceptions import AccessError

            raise AccessError(_("Seule la RH peut créer un contrat."))
        contract = self.env["pe.employment.contract"].create(
            self._contract_create_vals(contract_type="cdi")
        )
        return self._contract_form_action(contract, title=_("Nouveau contrat"))

    def action_open_active_contract(self):
        self.ensure_one()
        if self.active_contract_id:
            return self._contract_form_action(
                self.active_contract_id,
                title=_("Contrat actif — %s") % self.display_name,
            )
        return self.action_create_contract()

    def _action_generate_contract_template(self, contract_subtype):
        self.ensure_one()
        if not self.env.user.has_group("people_engine.group_hr"):
            from odoo.exceptions import AccessError

            raise AccessError(_("Seule la RH peut générer un contrat."))
        template = self.env["pe.document.template"].search(
            [
                ("document_type", "=", "contract"),
                ("contract_subtype", "=", contract_subtype),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not template:
            from odoo.exceptions import UserError

            raise UserError(
                _("Aucun modèle de contrat %s trouvé dans la banque RH.")
                % contract_subtype.upper()
            )
        draft = self.contract_ids.filtered(
            lambda c: c.contract_type == contract_subtype and c.statut == "draft"
        )[:1]
        if not draft:
            draft = self.env["pe.employment.contract"].create(
                self._contract_create_vals(contract_type=contract_subtype)
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Contrat %s — %s")
            % (contract_subtype.upper(), self.display_name),
            "res_model": "pe.personalize.document.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_profile_id": self.id,
                "default_template_id": template.id,
                "default_template_ids": [(6, 0, template.ids)],
            },
        }

    def action_generate_contract_cdd(self):
        return self._action_generate_contract_template("cdd")

    def action_generate_contract_cdi(self):
        return self._action_generate_contract_template("cdi")

    def action_generate_contract_freelance(self):
        return self._action_generate_contract_template("freelance")

    def action_open_onboarding_assistant(self):
        self.ensure_one()
        if not self.env.user.has_group("people_engine.group_hr"):
            from odoo.exceptions import AccessError

            raise AccessError(_("Seule la RH peut lancer l'assistant onboarding."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Assistant onboarding — %s") % self.display_name,
            "res_model": "pe.profile.onboarding.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_profile_id": self.id,
                "default_salaire_base": self.salaire_base,
                "default_devise_remuneration": self.devise_remuneration or "MAD",
            },
        }

    def _compute_alert_count(self):
        engine = PeopleEngineScoreEngine(self.env)
        for rec in self:
            metrics = PeopleEngineCollector().collect_all(
                rec, rec.metric_period_start, rec.metric_period_end
            )
            scores = engine.calculate_score(rec, metrics)
            rec.alert_count = len(engine.detect_alerts(rec, scores))

    def _get_period_dates(self):
        self.ensure_one()
        end = self.metric_period_end or date.today()
        if self.metric_period_days == "7":
            start = end - timedelta(days=7)
        elif self.metric_period_days == "90":
            start = end - timedelta(days=90)
        elif self.metric_period_start:
            start = self.metric_period_start
        else:
            start = end - timedelta(days=30)
        return start, end

    def action_refresh_metrics(self):
        collector = PeopleEngineCollector()
        for profile in self:
            start, end = profile._get_period_dates()
            metrics = collector.collect_all(profile, start, end)
            collector.apply_to_profile(profile, metrics, start, end)
        return True

    def action_calculate_score(self, manual_quality_score=None, calculated_by="manual"):
        if self.env.context.get("pe_skip_score_recalc"):
            return True
        return self.with_context(pe_skip_score_recalc=True)._action_calculate_score_impl(
            manual_quality_score=manual_quality_score,
            calculated_by=calculated_by,
        )

    def _action_calculate_score_impl(
        self, manual_quality_score=None, calculated_by="manual"
    ):
        engine = PeopleEngineScoreEngine(self.env)
        collector = PeopleEngineCollector()
        for profile in self:
            start, end = profile._get_period_dates()
            metrics = collector.collect_all(profile, start, end)
            collector.apply_to_profile(profile, metrics, start, end)
            scores = engine.calculate_score(profile, metrics, manual_quality_score)
            previous = engine._get_previous_score(profile)
            trend = "stable"
            trend_pct = 0.0
            if previous is not None:
                delta = scores["global"] - previous
                trend_pct = (delta / previous * 100) if previous else 0
                if delta > 2:
                    trend = "up"
                elif delta < -2:
                    trend = "down"
            profile.write(
                {
                    "score_performance": scores["performance_total"],
                    "score_engagement": scores["engagement_total"],
                    "score_growth": scores["growth_total"],
                    "score_global": scores["global"],
                    "objectives_achievement_pct": scores.get(
                        "objectives_achievement_pct", 0.0
                    ),
                    "score_trend": trend,
                    "score_trend_percent": trend_pct,
                    "last_score_update": fields.Datetime.now(),
                }
            )
            self.env["pe.performance.score"].create(
                {
                    "profile_id": profile.id,
                    "period_start": start,
                    "period_end": end,
                    "period_type": "monthly",
                    "score_objectives": scores["objectives"],
                    "score_quality": scores["quality"],
                    "score_business_impact": scores["impact"],
                    "score_performance_total": scores["performance_total"],
                    "score_participation": scores["participation"],
                    "score_collaboration": scores["collaboration"],
                    "score_process": scores["process"],
                    "score_engagement_total": scores["engagement_total"],
                    "score_progression": scores["progression"],
                    "score_training": scores["training"],
                    "score_development": scores["development"],
                    "score_growth_total": scores["growth_total"],
                    "score_global": scores["global"],
                    "previous_score": previous or 0,
                    "trend": trend,
                    "calculated_by": calculated_by,
                }
            )
            snapshot = self.env["pe.metric.snapshot"].create(
                {
                    "profile_id": profile.id,
                    "snapshot_date": end,
                    "period_start": start,
                    "period_end": end,
                    "score_global": scores["global"],
                    "score_performance": scores["performance_total"],
                    "score_engagement": scores["engagement_total"],
                    "score_growth": scores["growth_total"],
                }
            )
            snapshot.set_metrics(metrics)
            self.env["pe.action.log"].log_action(
                profile,
                "score_calculated",
                _("Score calculé : %.1f/100") % scores["global"],
                actor_type="system" if calculated_by == "auto" else "hr",
                score_before=previous or 0,
                score_after=scores["global"],
            )
            alerts = engine.detect_alerts(profile, scores)
            if alerts and profile.score_global < 60:
                profile.pe_status = "monitoring"
            PeopleEngineAlertService(self.env).notify_manager_alerts(profile, alerts)
            self.env["pe.gamification.engine"].check_and_award_badges(
                profile, previous
            )
        return True

    def action_praise(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Féliciter"),
            "res_model": "pe.celebration.manual.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_profile_id": self.id,
                "default_from_profile": True,
            },
        }

    def action_start_coaching(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Coaching IA"),
            "res_model": "pe.coaching.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_profile_id": self.id,
                "default_wizard_mode": "session",
                "default_use_ai": True,
            },
        }

    def action_open_learning_path_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Parcours formation (LMS)"),
            "res_model": "pe.coaching.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_profile_id": self.id,
                "default_wizard_mode": "plan",
                "default_use_ai": True,
            },
        }

    def action_open_evaluation_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Nouvelle évaluation"),
            "res_model": "pe.evaluation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_profile_id": self.id},
        }

    @api.model
    def _cron_calculate_all_scores(self):
        profiles = self.search([("pe_status", "!=", "inactive")])
        profiles.action_refresh_metrics()
        profiles.action_calculate_score(calculated_by="auto")
        return True

    @api.model
    def _cron_send_weekly_alerts(self):
        PeopleEngineAlertService(self.env).send_weekly_digest()
        return True

    @api.model
    def create_profiles_for_employees(self):
        """Crée un profil pour chaque employé interne B2B actif sans profil."""
        Employee = self.env["hr.employee"]
        existing = self.search([]).mapped("employee_id").ids
        to_create = Employee.search(
            [("id", "not in", existing), ("active", "=", True)]
        )
        count = 0
        for emp in to_create:
            user = emp.user_id
            if user and user.doorway_segment == "b2c":
                continue
            self.create({"employee_id": emp.id})
            count += 1
        return count

    @api.model
    def rh_hub_snapshot(self):
        """Données hub RH OWL (profil courant + KPIs).

        Lecture seule : agrège des données RH RÉELLES déjà persistées par le
        module (parcours, paie temps réel, évaluations, congés, juridique) pour
        alimenter le tableau de bord OWL. N'écrit rien et reste rétro-compatible
        (les anciennes clés employee/performance/dev_plan/hr_docs sont conservées).
        """
        user = self.env.user
        employee = self.env["hr.employee"].pe_resolve_user_employee(user)
        if not employee:
            return {"error": "no_employee"}
        profile = self.search([("employee_id", "=", employee.id)], limit=1)
        if not profile:
            profile = self.create({"employee_id": employee.id})
        paths = self.env["pe.learning.path"].search(
            [("profile_id", "=", profile.id), ("status", "=", "active")]
        )
        path_progress = 0.0
        if paths:
            progresses = [p.completion_percent or 0.0 for p in paths]
            path_progress = sum(progresses) / len(progresses)
        enrollments = self.env["pe.enrollment"].search(
            [("profile_id", "=", profile.id)]
        )
        docs_done = len(enrollments.filtered(lambda e: e.status == "completed"))
        docs_total = max(len(enrollments), 1)
        legal_count = self.env["pe.legal.article"].search_count([])
        coaching_open = 0
        for plan in profile.coaching_plan_ids:
            st = getattr(plan, "state", None) or getattr(plan, "status", "")
            if st != "done":
                coaching_open += 1
        perf_pct = min(100.0, max(0.0, profile.score_global or 0.0))

        # ── Plan de développement : parcours nommés + progression réelle ──
        dev_items = []
        dev_paths = self.env["pe.learning.path"].search(
            [
                ("profile_id", "=", profile.id),
                ("status", "in", ["active", "pending", "completed"]),
            ],
            order="completion_percent desc, create_date desc",
            limit=6,
        )
        status_labels = dict(
            self.env["pe.learning.path"]._fields["status"].selection
        )
        for p in dev_paths:
            dev_items.append(
                {
                    "name": p.name or "Parcours",
                    "percent": round(p.completion_percent or 0.0),
                    "status": status_labels.get(p.status, p.status or ""),
                }
            )

        # ── Série de performance (area chart) depuis les snapshots métriques ──
        perf_series = []
        snaps = self.env["pe.metric.snapshot"].search(
            [("profile_id", "=", profile.id)],
            order="snapshot_date asc",
            limit=12,
        )
        for s in snaps:
            perf_series.append(
                {
                    "label": s.snapshot_date.strftime("%d/%m")
                    if s.snapshot_date
                    else "",
                    "value": min(100.0, max(0.0, s.score_global or 0.0)),
                }
            )

        # ── Paie temps réel + heures du mois (lecture seule, mois courant) ──
        mois = fields.Date.context_today(self).strftime("%Y-%m")
        payslip = self.env["pe.payslip.live"].search(
            [("employee_id", "=", employee.id), ("mois", "=", mois)],
            limit=1,
        )
        hours_month = payslip.heures_reelles_mois if payslip else None
        net_pay = payslip.total_net_estime if payslip else None
        currency = (
            payslip.devise_base
            if payslip
            else (profile.devise_remuneration or "MAD")
        )

        # ── Solde de congés (allocations validées − congés pris validés) ──
        leave_remaining = None
        try:
            allocs = self.env["hr.leave.allocation"].search(
                [("employee_id", "=", employee.id), ("state", "=", "validate")]
            )
            taken = self.env["hr.leave"].search(
                [("employee_id", "=", employee.id), ("state", "=", "validate")]
            )
            leave_remaining = round(
                sum(allocs.mapped("number_of_days"))
                - sum(taken.mapped("number_of_days")),
                1,
            )
        except Exception:
            leave_remaining = None

        # ── Prochaine évaluation planifiée (period_end à venir, non clôturée) ──
        next_eval = None
        today = fields.Date.context_today(self)
        ev = self.env["pe.evaluation"].search(
            [
                ("employee_id", "=", employee.id),
                ("period_end", ">=", today),
                ("status", "not in", ["completed", "cancelled"]),
            ],
            order="period_end asc",
            limit=1,
        )
        if ev and ev.period_end:
            next_eval = ev.period_end.isoformat()

        # ── Documents juridiques réels (base de connaissance droit du travail) ──
        legal_docs = []
        cat_labels = dict(
            self.env["pe.legal.article"]._fields["category"].selection
        )
        for art in self.env["pe.legal.article"].search(
            [], order="is_current desc, id desc", limit=4
        ):
            legal_docs.append(
                {
                    "title": art.title or art.code or "Document",
                    "category": cat_labels.get(art.category, art.category or ""),
                    "current": bool(art.is_current),
                }
            )

        return {
            "employee": {
                "id": employee.id,
                "name": employee.name,
                "first_name": (employee.name or "").split(" ")[0],
                "job": employee.job_id.name or "",
                "department": employee.department_id.name or "",
                "email": user.email or "",
            },
            "performance": {
                "score_global": profile.score_global,
                "percent": perf_pct,
                "band": profile.performance_band or "",
                "trend": profile.score_trend or "stable",
            },
            "kpis": {
                "leave_remaining": leave_remaining,
                "hours_month": hours_month,
                "score_percent": round(perf_pct),
                "next_eval": next_eval,
            },
            "perf_series": perf_series,
            "dev_plan": {
                "active_paths": len(paths),
                "progress_pct": round(path_progress, 1),
                "coaching_plans": coaching_open,
                "items": dev_items,
            },
            "payroll": {
                "net": net_pay,
                "currency": currency,
                "month": mois,
                "hours": hours_month,
                "has_payslip": bool(payslip),
            },
            "legal_docs": legal_docs,
            "hr_docs": {
                "enrollments_total": len(enrollments),
                "enrollments_done": docs_done,
                "completion_pct": round(100.0 * docs_done / docs_total, 1),
                "legal_articles": legal_count,
            },
        }

    @staticmethod
    def _safe_float_sum(values):
        """Somme robuste (None/False → 0) pour agrégats paie / KPI."""
        total = 0.0
        for value in values:
            try:
                total += float(value or 0.0)
            except (TypeError, ValueError):
                continue
        return total

    @api.model
    def rh_global_snapshot(self):
        """Vue d'ensemble RH (superviseur / global) — agrégats temps réel.

        Lecture seule et SÉCURISÉE : on ne force aucun sudo, donc les règles
        d'enregistrement (ir.rule) s'appliquent naturellement — un responsable RH
        / admin voit toute l'entreprise (rule_profile_hr = tous), un gestionnaire
        voit son équipe directe (rule_profile_manager). Aucune donnée fabriquée :
        tout provient des profils, parcours, paie temps réel et évaluations déjà
        persistés. Renvoie un état vide cohérent si aucun profil n'est visible.
        """
        try:
            profiles = self.search([])
            headcount = len(profiles)
            if not headcount:
                return {"scope": "empty", "headcount": 0}

            band_field = self._fields["performance_band"]
            band_selection = band_field.selection
            if callable(band_selection):
                band_selection = band_selection(self.env)
            band_labels = dict(band_selection or [])

            scores = [p.score_global or 0.0 for p in profiles]
            avg_score = round(sum(scores) / headcount, 1)

            bands = []
            for key, label in band_selection or []:
                count = len(
                    profiles.filtered(lambda p, k=key: p.performance_band == k)
                )
                bands.append(
                    {
                        "key": key,
                        "label": label,
                        "count": count,
                        "pct": round(100.0 * count / headcount),
                    }
                )

            trends = {"up": 0, "stable": 0, "down": 0}
            for p in profiles:
                t = p.score_trend or "stable"
                trends[t] = trends.get(t, 0) + 1

            # ── Parcours de formation (équipe visible) ──
            Path = self.env["pe.learning.path"]
            active_paths = Path.search(
                [("profile_id", "in", profiles.ids), ("status", "=", "active")]
            )
            avg_path = (
                round(
                    self._safe_float_sum(active_paths.mapped("completion_percent"))
                    / len(active_paths),
                    1,
                )
                if active_paths
                else 0.0
            )

            # ── Coaching ouvert (toutes les fiches visibles) ──
            coaching_open = 0
            for p in profiles:
                for plan in p.coaching_plan_ids:
                    st = getattr(plan, "state", None) or getattr(plan, "status", "")
                    if st != "done":
                        coaching_open += 1

            # ── Formations ──
            enr = self.env["pe.enrollment"].search(
                [("profile_id", "in", profiles.ids)]
            )
            enr_done = len(enr.filtered(lambda e: e.status == "completed"))
            enr_total = len(enr)

            # ── Évaluations en attente ──
            pending_eval = self.env["pe.evaluation"].search_count(
                [
                    ("profile_id", "in", profiles.ids),
                    ("status", "in", ["draft", "pending_review", "pending_approval"]),
                ]
            )

            # ── Paie temps réel agrégée (mois courant, employés visibles) ──
            mois = fields.Date.context_today(self).strftime("%Y-%m")
            slips = self.env["pe.payslip.live"].search(
                [
                    ("employee_id", "in", profiles.mapped("employee_id").ids),
                    ("mois", "=", mois),
                ]
            )
            payroll_net = round(self._safe_float_sum(slips.mapped("total_net_estime")))
            hours_total = round(
                self._safe_float_sum(slips.mapped("heures_reelles_mois"))
            )
            currency = slips[:1].devise_base if slips else "MAD"

            # ── Classement performance (top profils visibles) ──
            ranked = profiles.sorted(
                key=lambda p: p.score_global or 0.0, reverse=True
            )
            top = ranked[:6]
            top_performers = [
                {
                    "id": p.employee_id.id,
                    "name": p.employee_id.name or "—",
                    "score": round(p.score_global or 0.0),
                    "band": band_labels.get(p.performance_band, ""),
                    "trend": p.score_trend or "stable",
                }
                for p in top
                if p.employee_id
            ]
            score_bars = [
                {
                    "label": (p.employee_id.name or "—").split(" ")[0],
                    "value": min(100.0, max(0.0, p.score_global or 0.0)),
                }
                for p in top
                if p.employee_id
            ]

            return {
                "scope": "hr"
                if self.env.user.has_group("people_engine.group_hr")
                else "manager",
                "headcount": headcount,
                "kpis": {
                    "headcount": headcount,
                    "avg_score": round(avg_score),
                    "active_paths": len(active_paths),
                    "pending_eval": pending_eval,
                },
                "bands": bands,
                "trends": trends,
                "training": {
                    "avg_path": avg_path,
                    "enr_done": enr_done,
                    "enr_total": enr_total,
                    "completion_pct": round(100.0 * enr_done / enr_total, 1)
                    if enr_total
                    else 0.0,
                    "coaching_open": coaching_open,
                },
                "payroll": {
                    "net": payroll_net,
                    "currency": currency,
                    "hours": hours_total,
                    "headcount_paid": len(slips),
                    "has_data": bool(slips),
                },
                "score_bars": score_bars,
                "top_performers": top_performers,
            }
        except Exception as exc:
            _logger.exception("rh_global_snapshot failed")
            return {"error": str(exc), "headcount": 0}
