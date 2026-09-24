import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

from .crm_team_pipeline import (
    PROVENANCE_PIPELINE_TEAM_XMLIDS,
    _provenance_stage_xmlid,
)

# Revenu attendu par défaut à la création (démo / pipeline kanban)
PIPELINE_DEFAULT_REVENUE = {
    "renovation": 8500.0,
    "immobilier": 12000.0,
    "marketing": 1200.0,
    "driven": 25000.0,
    "assurance": 1800.0,
    "doorway_clients": 3600.0,
    "sales": 5000.0,
}

PIPELINE_TEAM_XMLID_TO_REVENUE_KEY = {
    "renovation_conciergerie.crm_team_renovation": "renovation",
    "renovation_conciergerie.crm_team_immobilier": "immobilier",
    "renovation_conciergerie.crm_team_marketing": "marketing",
    "renovation_conciergerie.crm_team_driven": "driven",
    "renovation_conciergerie.crm_team_assurance": "assurance",
    "renovation_conciergerie.crm_team_doorway_b2b": "doorway_clients",
}

PROVENANCE_TO_STAGE_SUFFIX = {
    "nouveau": "new",
    "social": "social",
    "retell": "retell",
    "website": "website",
}

# Probabilité de démo lorsque le scoring Odoo est à 0 % (ex. pipeline Sales legacy)
STAGE_NAME_DEFAULT_PROBABILITY = (
    ("gagne", 100.0),
    ("gagné", 100.0),
    ("won", 100.0),
    ("perdu", 0.0),
    ("lost", 0.0),
    ("nouveau", 10.0),
    ("reseau", 15.0),
    ("retell", 25.0),
    ("site web", 30.0),
    ("qualif", 50.0),
    ("relance", 35.0),
    ("attente", 45.0),
    ("document", 55.0),
    ("rappel", 40.0),
    ("devis", 65.0),
    ("analyse", 45.0),
)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model
    def _doorway_crm_peer_sales_domain(self):
        """Martin / Zakaria : uniquement leurs leads (+ non assignés), pas l'autre vendeur."""
        user = self.env.user
        if user._doorway_is_crm_superuser():
            return []
        if not user._doorway_is_crm_peer_sales_user():
            return []
        return ["|", ("user_id", "=", user.id), ("user_id", "=", False)]

    @api.model
    def _doorway_apply_peer_sales_domain(self, domain):
        extra = self._doorway_crm_peer_sales_domain()
        if extra:
            return expression.AND([domain or [], extra])
        return domain

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        return super().search(
            self._doorway_apply_peer_sales_domain(domain),
            offset=offset,
            limit=limit,
            order=order,
        )

    @api.model
    def search_count(self, domain, limit=None):
        return super().search_count(
            self._doorway_apply_peer_sales_domain(domain), limit=limit
        )

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        return super().read_group(
            self._doorway_apply_peer_sales_domain(domain),
            fields,
            groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )

    def check_access_rule(self, operation):
        super().check_access_rule(operation)
        extra = self._doorway_crm_peer_sales_domain()
        if not extra:
            return
        forbidden = self.filtered(
            lambda lead: lead.user_id
            and lead.user_id != self.env.user
        )
        if forbidden:
            raise AccessError(
                _("Vous n'avez pas accès à ce lead assigné à un autre vendeur.")
            )

    is_marketing_pipeline = fields.Boolean(
        string="Pipeline Marketing",
        compute="_compute_pipeline_flags",
        store=True,
    )
    is_driven_pipeline = fields.Boolean(
        string="Pipeline Driven",
        compute="_compute_pipeline_flags",
        store=True,
    )
    is_renovation_pipeline = fields.Boolean(
        string="Pipeline Rénovation",
        compute="_compute_pipeline_flags",
        store=True,
    )
    doorway_segment = fields.Selection(
        [
            ("b2b", "B2B"),
            ("b2c", "B2C"),
        ],
        string="Segment Doorway",
        compute="_compute_doorway_segment",
        store=True,
        index=True,
        help="B2C : pipelines Rénovation, Assurance et Immobilier. "
        "B2B : Marketing, Doorway Clients et Driven.",
    )
    team_uses_provenance_stages = fields.Boolean(
        related="team_id.uses_provenance_stages",
        readonly=True,
    )

    # --- Marketing ---
    lead_provenance = fields.Selection(
        [
            ("nouveau", "Nouveau"),
            ("social", "Réseaux sociaux"),
            ("retell", "Agent IA"),
            ("website", "Site web"),
        ],
        string="Provenance",
        tracking=True,
        default="nouveau",
    )
    marketing_company_type = fields.Char(
        string="Type d'entreprise",
        tracking=True,
    )
    marketing_need_social = fields.Boolean(string="Réseaux sociaux", tracking=True)
    marketing_need_ai_agent = fields.Boolean(string="Agent IA", tracking=True)
    marketing_need_crm = fields.Boolean(string="CRM", tracking=True)
    marketing_need_seo = fields.Boolean(string="SEO", tracking=True)
    marketing_need_website = fields.Boolean(string="Site web", tracking=True)
    marketing_need_lead_gen = fields.Boolean(string="Lead generation", tracking=True)
    marketing_monthly_budget = fields.Monetary(
        string="Budget mensuel",
        currency_field="company_currency",
        tracking=True,
    )
    marketing_already_has_agency = fields.Boolean(
        string="Déjà avec une agence",
        tracking=True,
    )

    # --- Driven (financement) ---
    DRIVEN_MIN_CREDIT_SCORE = 600
    DRIVEN_MIN_MONTHS_IN_BUSINESS = 6
    DRIVEN_MIN_MONTHLY_REVENUE = 10000.0

    driven_company_type = fields.Char(
        string="Type d'entreprise",
        tracking=True,
    )
    driven_credit_score = fields.Integer(
        string="Score de crédit",
        tracking=True,
    )
    driven_months_in_business = fields.Integer(
        string="Mois en activité",
        tracking=True,
    )
    driven_monthly_revenue = fields.Monetary(
        string="Revenu mensuel",
        currency_field="company_currency",
        tracking=True,
    )
    driven_working_capital_need = fields.Text(
        string="Besoin de fonds de roulement",
        tracking=True,
    )
    driven_credit_score_ok = fields.Boolean(
        string="Score de 600 et plus",
        compute="_compute_driven_eligibility",
        store=True,
    )
    driven_months_ok = fields.Boolean(
        string="6 mois en activité et plus",
        compute="_compute_driven_eligibility",
        store=True,
    )
    driven_revenue_ok = fields.Boolean(
        string="10 000 $ et plus de revenu mensuel",
        compute="_compute_driven_eligibility",
        store=True,
    )
    driven_eligible = fields.Boolean(
        string="Critères Driven remplis",
        compute="_compute_driven_eligibility",
        store=True,
    )

    @api.model
    def _normalize_team_name(self, name):
        """Minuscules sans accents pour matcher les clés de revenu."""
        if not name:
            return ""
        lowered = (name or "").lower()
        decomposed = unicodedata.normalize("NFD", lowered)
        return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")

    @api.model
    def _get_default_revenue_by_pipeline(self, team_id):
        """
        Revenu par défaut selon le pipeline (équipe CRM).
        Utilisé à la création et pour le backfill des leads à 0 $.
        """
        if not team_id:
            return 0.0
        team = self.env["crm.team"].browse(team_id)
        if not team.exists():
            return 0.0

        for xmlid, revenue_key in PIPELINE_TEAM_XMLID_TO_REVENUE_KEY.items():
            ref_team = self.env.ref(xmlid, raise_if_not_found=False)
            if ref_team and ref_team.id == team.id:
                return PIPELINE_DEFAULT_REVENUE.get(revenue_key, 0.0)

        normalized = self._normalize_team_name(team.name)
        for key, value in PIPELINE_DEFAULT_REVENUE.items():
            if key.replace("_", " ") in normalized or key in normalized:
                return value
        # Pipeline historique « Agence Doorway » / Sales (hors modules Doorway)
        if "agence doorway" in normalized or normalized in ("sales", "ventes"):
            return PIPELINE_DEFAULT_REVENUE["sales"]
        return 0.0

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "expected_revenue" in fields_list and not defaults.get("expected_revenue"):
            team_id = defaults.get("team_id") or self.env.context.get("default_team_id")
            revenue = self._get_default_revenue_by_pipeline(team_id)
            if revenue:
                defaults["expected_revenue"] = revenue
        return defaults

    @api.model
    def _backfill_expected_revenue(self):
        """Renseigne expected_revenue sur les leads actifs encore à 0."""
        leads = self.search(
            [("active", "=", True), ("expected_revenue", "=", 0), ("team_id", "!=", False)]
        )
        updated = 0
        for lead in leads:
            revenue = self._get_default_revenue_by_pipeline(lead.team_id.id)
            if revenue:
                lead.expected_revenue = revenue
                updated += 1
        return updated

    @api.model
    def _default_probability_for_stage(self, stage):
        """Probabilité indicative par nom d'étape (démo si scoring Odoo = 0)."""
        if not stage:
            return 10.0
        if stage.is_won:
            return 100.0
        normalized = self._normalize_team_name(stage.name)
        for key, prob in STAGE_NAME_DEFAULT_PROBABILITY:
            if key in normalized:
                return prob
        return 40.0

    @api.model
    def _backfill_lead_probability(self):
        """Aligne la probabilité des leads actifs encore à 0 % (revenu pondéré kanban)."""
        leads = self.search([("active", "=", True), ("probability", "<=", 0)])
        updated = 0
        for lead in leads:
            prob = lead.automated_probability or 0.0
            if prob <= 0:
                prob = self._default_probability_for_stage(lead.stage_id)
            lead.write({"probability": prob, "automated_probability": prob})
            updated += 1
        return updated

    def _get_provenance_team_xmlid(self):
        self.ensure_one()
        if not self.team_id:
            return False
        for team_xmlid in PROVENANCE_PIPELINE_TEAM_XMLIDS:
            team = self.env.ref(team_xmlid, raise_if_not_found=False)
            if team and team.id == self.team_id.id:
                return team_xmlid
        return False

    def _get_stage_from_provenance(self, provenance):
        if not self.team_id.uses_provenance_stages:
            return self.env["crm.stage"]
        suffix = PROVENANCE_TO_STAGE_SUFFIX.get(provenance)
        team_xmlid = self._get_provenance_team_xmlid()
        if not suffix or not team_xmlid:
            return self.env["crm.stage"]
        return self.env.ref(
            _provenance_stage_xmlid(team_xmlid, suffix), raise_if_not_found=False
        ) or self.env["crm.stage"]

    @api.model
    def _cleanup_doorway_test_leads(self):
        """Supprime les opportunités créées lors des tests (webhooks, Meta, ping)."""
        Lead = self.env["crm.lead"].sudo()
        clauses = [
            [("name", "=like", "Ping —%")],
            [("name", "=like", "RealTest%")],
            [("name", "=like", "Jean Test%")],
            [("name", "=like", "Test —%")],
            [("name", "=", "Opportunité de test")],
            [("name", "ilike", "Validation Meta%")],
            [("name", "ilike", "Val2 Meta%")],
            [("name", "ilike", "E2E%")],
            [("name", "ilike", "Hub E2E%")],
            [("name", "ilike", "Test ProdE2E%")],
            [("name", "ilike", "TEST E2E%")],
            [("contact_name", "ilike", "E2E%")],
            [("email_from", "ilike", "%test.intellixcrm.com")],
            [("email_from", "ilike", "e2e.%@agencedoorway.com")],
            [("email_from", "ilike", "hub.e2e@%")],
            [
                (
                    "immo_meta_lead_id",
                    "in",
                    ("test-validation-001", "val-002"),
                )
            ],
        ]
        domain = expression.OR(clauses)
        test_leads = Lead.search(domain)
        count = len(test_leads)
        if test_leads:
            test_leads.unlink()
        return count

    @api.model
    def _doorway_martin_transfer_user(self, agent=None):
        """Vendeur cible du transfert humain (Martin par défaut)."""
        if agent and agent.transfer_user_id:
            return agent.transfer_user_id
        return (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    ("login", "=", "martin@agencedoorway.com"),
                    ("active", "=", True),
                    ("share", "=", False),
                ],
                limit=1,
            )
        )

    QUALIFIED_IA_STAGE_XMLID = (
        "renovation_conciergerie.crm_stage_renovation_immo_qualified"
    )

    @api.model
    def _doorway_ai_agent_entry_vals(self, team=None):
        """Lead entrant voix IA → colonne kanban Agent IA."""
        vals = {"lead_provenance": "retell"}
        if team:
            stage = (
                self.env["crm.lead"]
                .new({"team_id": team.id})
                ._get_stage_from_provenance("retell")
            )
            if stage:
                vals["stage_id"] = stage.id
        return vals

    @api.model
    def _doorway_ia_qualified_vals(self, team=None):
        """Lead qualifié par l'IA → colonne Qualifié (IA)."""
        stage = self.env.ref(
            self.QUALIFIED_IA_STAGE_XMLID, raise_if_not_found=False
        )
        if not stage:
            return {}
        if team and team not in stage.team_ids:
            return {}
        return {"stage_id": stage.id}

    @api.model
    def _doorway_human_transfer_vals(self, agent=None, team=None):
        """Colonne kanban Agent IA + assignation Martin après transfert téléphonique."""
        user = self._doorway_martin_transfer_user(agent)
        if team and team.id in (92, 93):
            login = (
                self.env["ir.config_parameter"].sudo().get_param(
                    "doorway.immo_reno_qualifier_login"
                )
                or "hiba@agencedoorway.com"
            )
            hiba = self.env["res.users"].sudo().search(
                [("login", "=", login), ("active", "=", True), ("share", "=", False)],
                limit=1,
            )
            if hiba:
                user = hiba
        vals = {"lead_provenance": "retell"}
        if user:
            vals["user_id"] = user.id
        transfer_tag = self.env.ref(
            "renovation_conciergerie.crm_tag_transfert_humain",
            raise_if_not_found=False,
        )
        if transfer_tag:
            vals["tag_ids"] = [(4, transfer_tag.id)]
        if team:
            stage = (
                self.env["crm.lead"]
                .new({"team_id": team.id})
                ._get_stage_from_provenance("retell")
            )
            if stage:
                vals["stage_id"] = stage.id
        return vals

    def _apply_provenance_stage(self):
        """Place le lead sur la colonne kanban correspondant à sa provenance."""
        for lead in self.filtered(
            lambda l: l.team_id.uses_provenance_stages and l.lead_provenance
        ):
            stage = lead._get_stage_from_provenance(lead.lead_provenance)
            if stage and lead.stage_id != stage:
                lead.stage_id = stage

    def _doorway_new_opportunity_defaults(self):
        """Équipe / vendeur par défaut pour une nouvelle opportunité (superviseur, etc.)."""
        team_id = (
            self.env.context.get("default_team_id")
            or self.env.context.get("renovation_active_pipeline_team_id")
        )
        if not team_id:
            team_id = self._get_kanban_pipeline_team_id(None)
        if not team_id and self.env.user.has_group(
            "renovation_conciergerie.group_pipeline_supervisor"
        ):
            allowed = self.env.user._allowed_pipeline_team_ids()
            team_id = allowed[:1].id if allowed else False
        if not team_id and self.env.user.sale_team_id:
            team_id = self.env.user.sale_team_id.id
        return {
            "default_type": "opportunity",
            "default_team_id": team_id,
            "default_user_id": self.env.uid,
            "default_lead_provenance": "nouveau",
        }

    def action_create_opportunity(self):
        """Ouvre le formulaire complet (bouton Nouvelle opportunité)."""
        self.env["crm.lead"].check_access("create")
        view = self.env.ref("crm.crm_lead_view_form", raise_if_not_found=False)
        action = {
            "type": "ir.actions.act_window",
            "name": _("Nouvelle opportunité"),
            "res_model": "crm.lead",
            "view_mode": "form",
            "target": "current",
            "context": self._doorway_new_opportunity_defaults(),
        }
        if view:
            action["views"] = [(view.id, "form")]
        return action

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("expected_revenue"):
                team_id = vals.get("team_id") or self.env.context.get("default_team_id")
                revenue = self._get_default_revenue_by_pipeline(team_id)
                if revenue:
                    vals["expected_revenue"] = revenue
            if self.env.user.has_group(
                "renovation_conciergerie.group_pipeline_supervisor"
            ):
                if not vals.get("team_id"):
                    team_id = vals.get("team_id") or self.env.context.get(
                        "default_team_id"
                    ) or self.env.context.get("renovation_active_pipeline_team_id")
                    if not team_id:
                        allowed = self.env.user._allowed_pipeline_team_ids()
                        team_id = allowed[:1].id if allowed else False
                    if team_id:
                        vals["team_id"] = team_id
                if not vals.get("user_id"):
                    vals["user_id"] = self.env.uid
        records = super().create(vals_list)
        records._apply_provenance_stage()
        return records

    def write(self, vals):
        if vals.get("team_id") and "expected_revenue" not in vals:
            revenue = self._get_default_revenue_by_pipeline(vals["team_id"])
            if revenue:
                zero_revenue = self.filtered(lambda l: not l.expected_revenue)
                if zero_revenue:
                    super(CrmLead, zero_revenue).write({"expected_revenue": revenue})
        res = super().write(vals)
        if {"lead_provenance", "team_id"} & set(vals):
            self._apply_provenance_stage()
        if vals.get("stage_id") and "probability" not in vals:
            zero_prob = self.filtered(lambda l: (l.probability or 0) <= 0)
            for lead in zero_prob:
                prob = lead.automated_probability or self._default_probability_for_stage(
                    lead.stage_id
                )
                if prob > 0:
                    lead.write({"probability": prob, "automated_probability": prob})
        return res

    @api.onchange("lead_provenance")
    def _onchange_lead_provenance(self):
        if self.team_id.uses_provenance_stages and self.lead_provenance:
            stage = self._get_stage_from_provenance(self.lead_provenance)
            if stage:
                self.stage_id = stage

    @api.onchange("team_id")
    def _onchange_team_id_assignation(self):
        """Réinitialise le vendeur si hors de l'équipe et propose la 1re étape du pipeline."""
        if not self.team_id:
            return
        team_users = self.team_id.member_ids | self.team_id.user_id
        if self.user_id and self.user_id not in team_users:
            self.user_id = self.team_id.user_id or False
        if (
            not self.stage_id
            or (self.stage_id.team_ids and self.team_id not in self.stage_id.team_ids)
        ):
            self.stage_id = self._stage_find(domain=[("fold", "=", False)])

    @api.depends("team_id")
    def _compute_pipeline_flags(self):
        marketing = self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )
        driven = self.env.ref(
            "renovation_conciergerie.crm_team_driven", raise_if_not_found=False
        )
        renovation = self.env.ref(
            "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
        )

        for lead in self:
            team = lead.team_id
            lead.is_marketing_pipeline = bool(marketing and team == marketing)
            lead.is_driven_pipeline = bool(driven and team == driven)
            lead.is_renovation_pipeline = bool(renovation and team == renovation)

    @api.depends("team_id")
    def _compute_doorway_segment(self):
        Team = self.env["crm.team"]
        for lead in self:
            lead.doorway_segment = Team.doorway_segment_for_team(lead.team_id)

    @api.model
    def _backfill_doorway_segment(self):
        """Recalcule le segment B2B/B2C sur les opportunités existantes."""
        leads = self.search([("team_id", "!=", False)])
        if leads:
            leads._compute_doorway_segment()

    @api.depends(
        "driven_credit_score",
        "driven_months_in_business",
        "driven_monthly_revenue",
        "is_driven_pipeline",
    )
    def _compute_driven_eligibility(self):
        min_score = self.DRIVEN_MIN_CREDIT_SCORE
        min_months = self.DRIVEN_MIN_MONTHS_IN_BUSINESS
        min_revenue = self.DRIVEN_MIN_MONTHLY_REVENUE
        for lead in self:
            lead.driven_credit_score_ok = (lead.driven_credit_score or 0) >= min_score
            lead.driven_months_ok = (lead.driven_months_in_business or 0) >= min_months
            lead.driven_revenue_ok = (lead.driven_monthly_revenue or 0) >= min_revenue
            lead.driven_eligible = (
                lead.is_driven_pipeline
                and lead.driven_credit_score_ok
                and lead.driven_months_ok
                and lead.driven_revenue_ok
            )

    @api.model
    def _backfill_driven_eligibility(self):
        """Recalcule les coches Driven après changement des seuils (>=)."""
        leads = self.search([("team_id.name", "=", "Driven")])
        if leads:
            leads._compute_driven_eligibility()

    def _get_kanban_pipeline_team_id(self, search_domain=None):
        """Équipe active pour le kanban (contexte action ou filtre)."""
        team_id = self.env.context.get("default_team_id")
        if team_id:
            return team_id
        search_teams = self.env.context.get("search_default_team_id")
        if isinstance(search_teams, (list, tuple)) and len(search_teams) == 1:
            return search_teams[0]
        renovation_team = self.env.context.get("renovation_active_pipeline_team_id")
        if renovation_team:
            return renovation_team
        if search_domain:
            for leaf in search_domain:
                if not isinstance(leaf, (list, tuple)) or len(leaf) < 3:
                    continue
                if leaf[0] != "team_id":
                    continue
                if leaf[1] == "=" and leaf[2]:
                    return leaf[2]
                if leaf[1] == "in" and len(leaf[2]) == 1:
                    return leaf[2][0]
        return False

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Colonnes kanban = uniquement les étapes du pipeline actif (sans doublons)."""
        team_id = self._get_kanban_pipeline_team_id(domain)
        if team_id:
            team = self.env["crm.team"].browse(team_id)
            if team.uses_provenance_stages:
                dedicated = self.env["crm.stage"].search(
                    [("team_ids", "in", team.id)], order="sequence, id"
                )
                if dedicated:
                    return dedicated
        return super()._read_group_stage_ids(stages, domain)

    @api.model
    def _doorway_all_pipelines_action_context(self, base_context=None):
        """Contexte CRM : tous les pipelines Doorway, sans filtre d'équipe pré-appliqué."""
        ctx = dict(base_context or {})
        for key in (
            "default_team_id",
            "search_default_team_id",
            "renovation_active_pipeline_team_id",
            "search_default_assigned_to_me",
        ):
            ctx.pop(key, None)
        ctx.setdefault("default_type", "opportunity")
        ctx["show_user_team_stages"] = 0
        return ctx

    @api.model
    def action_open_all_crm_pipelines(self, *args):
        """Retour à la vue combinée (tous les pipelines)."""
        action = self.env["ir.actions.actions"]._for_xml_id(
            "renovation_conciergerie.doorway_action_pipeline_all"
        )
        ctx = self.env["crm.team"]._doorway_parse_action_context(action.get("context"))
        action["context"] = self._doorway_all_pipelines_action_context(ctx)
        action["display_name"] = _("Tous les pipelines")
        return action

    @api.model
    def _renovation_pipeline_action_context(self, base_context=None):
        """Contexte kanban pour le pipeline Rénovation (tous les leads de l'équipe)."""
        team = self.env.ref(
            "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
        )
        if not team:
            return base_context or {}
        ctx = dict(base_context or {})
        ctx.update(
            {
                "default_team_id": team.id,
                "search_default_team_id": [team.id],
                "show_user_team_stages": 0,
                "renovation_active_pipeline_team_id": team.id,
            }
        )
        ctx.pop("search_default_assigned_to_me", None)
        return ctx

    def action_switch_crm_pipeline(self):
        """Ouvre le pipeline filtré sur l'équipe choisie (boutons d'en-tête kanban)."""
        xmlid = self.env.context.get("renovation_pipeline_xmlid")
        team = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else False
        if not team:
            team_id = self.env.context.get("renovation_pipeline_team_id")
            if team_id:
                team = self.env["crm.team"].browse(int(team_id))
        if not team:
            return False

        marketing = self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )
        if marketing and team == marketing:
            return self.env["crm.team"]._action_open_doorway_pipeline(
                "renovation_conciergerie.doorway_action_pipeline_marketing",
                include_digital_doorway=True,
            )

        action = self.env["ir.actions.actions"]._for_xml_id("crm.crm_lead_action_pipeline")
        ctx = self.env["crm.team"]._doorway_parse_action_context(action.get("context"))
        if team == self.env.ref(
            "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
        ):
            ctx = self._renovation_pipeline_action_context(ctx)
        else:
            ctx.update(
                {
                    "default_team_id": team.id,
                    "search_default_team_id": [team.id],
                    "show_user_team_stages": 0,
                    "renovation_active_pipeline_team_id": team.id,
                }
            )
        action["context"] = ctx
        action["display_name"] = team.name
        if team.uses_provenance_stages:
            lead_types = ["opportunity"]
            if team.use_leads:
                lead_types = ["lead", "opportunity"]
            action["domain"] = [
                ("type", "in", lead_types),
                ("team_id", "=", team.id),
            ]
        return action

    @api.model
    def _doorway_cleanup_legacy_automation_rules(self):
        """Retire les règles de démo remplacées par automation_rules.xml (brief 2B)."""
        legacy_names = (
            "doorway_automation_renovation_qualification",
            "doorway_automation_renovation_qualification_action",
            "doorway_automation_renovation_followup",
            "doorway_automation_renovation_followup_action",
            "doorway_automation_renovation_website_create",
            "doorway_automation_renovation_website_create_action",
            "doorway_automation_renovation_retell_create",
            "doorway_automation_renovation_retell_create_action",
            "doorway_automation_marketing_qualification",
            "doorway_automation_marketing_qualification_action",
            "doorway_automation_driven_qualification",
            "doorway_automation_driven_qualification_action",
            "doorway_automation_driven_eligible",
            "doorway_automation_driven_eligible_action",
            "doorway_automation_lead_inactive_reminder",
            "doorway_automation_lead_inactive_reminder_action",
        )
        imd = self.env["ir.model.data"].sudo()
        automation = self.env["base.automation"].sudo()
        server = self.env["ir.actions.server"].sudo()
        for name in legacy_names:
            row = imd.search(
                [("module", "=", "renovation_conciergerie"), ("name", "=", name)],
                limit=1,
            )
            if not row:
                continue
            if row.model == "base.automation":
                rec = automation.browse(row.res_id)
                if rec.exists():
                    rec.action_server_ids.unlink()
                    rec.unlink()
            elif row.model == "ir.actions.server":
                rec = server.browse(row.res_id)
                if rec.exists():
                    rec.unlink()
            row.unlink()


class CrmStage(models.Model):
    _inherit = "crm.stage"

    @api.model
    def _renovation_rename_retell_stages(self):
        """Renomme les étapes CRM « Retell » en « Agent IA » (bases déjà installées)."""
        self.search([("name", "=", "Retell")]).write({"name": "Agent IA"})
