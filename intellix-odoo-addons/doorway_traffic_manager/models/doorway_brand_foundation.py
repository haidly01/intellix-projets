# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayBrandFoundation(models.Model):
    _name = "doorway.brand.foundation"
    _description = "Fondation de marque Traffic Manager"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "write_date desc"

    pipeline_id = fields.Many2one(
        "crm.team", required=True, string="Pipeline / Marque", tracking=True
    )
    state = fields.Selection(
        [
            ("draft", "Questionnaire en cours"),
            ("analyzing", "Analyse IA — validation requise"),
            ("validated", "Validé"),
        ],
        default="draft",
        tracking=True,
    )
    completion_pct = fields.Integer(
        string="Complétion %", compute="_compute_completion_pct"
    )
    allow_auto_pause = fields.Boolean(
        string="Pause auto si dépassement budget",
        default=False,
        help="Exception : met en pause automatiquement une campagne si le budget est dépassé.",
    )

    brand_name = fields.Char("Nom de la marque", required=True, tracking=True)
    brand_description = fields.Text("Description en 2-3 phrases")
    founding_year = fields.Integer("Année de création")
    geographic_zone = fields.Selection(
        [
            ("local", "Local (ville/région)"),
            ("national", "National"),
            ("france", "France"),
            ("canada", "Canada"),
            ("maroc", "Maroc"),
            ("international", "International"),
        ],
    )
    language_ids = fields.Many2many("res.lang", string="Langues de communication")

    target_b2c = fields.Boolean("Cible B2C (particuliers)", default=True)
    target_b2b = fields.Boolean("Cible B2B (entreprises)")
    target_age_min = fields.Integer("Âge minimum")
    target_age_max = fields.Integer("Âge maximum")
    target_gender = fields.Selection(
        [("all", "Tous"), ("male", "Hommes"), ("female", "Femmes")],
        default="all",
    )
    target_income = fields.Selection(
        [
            ("low", "Revenus modestes"),
            ("mid", "Classe moyenne"),
            ("high", "Revenus élevés"),
            ("luxury", "Premium / Luxe"),
        ],
    )
    target_pain_points = fields.Text("Problèmes principaux de la cible (1 par ligne)")
    target_desires = fields.Text("Désirs et aspirations de la cible (1 par ligne)")
    target_persona = fields.Text("Description du client idéal (persona)")

    price_positioning = fields.Selection(
        [
            ("economy", "Économique"),
            ("mid", "Milieu de gamme"),
            ("premium", "Premium"),
            ("luxury", "Luxe"),
        ],
    )
    main_value_prop = fields.Text("Proposition de valeur principale (1-2 phrases)")
    competitors = fields.Text("3-5 concurrents principaux (1 par ligne)")
    competitive_advantage = fields.Text(
        "En quoi êtes-vous meilleur que vos concurrents ?"
    )
    what_to_avoid = fields.Text("Ce que la marque NE fait PAS / NE dit PAS")

    brand_tone_ids = fields.Many2many(
        "doorway.brand.tone.tag", string="Ton de marque"
    )
    communication_style = fields.Selection(
        [("tutoiement", "Tutoiement (tu)"), ("vouvoiement", "Vouvoiement (vous)")],
        default="vouvoiement",
    )
    brand_taboos = fields.Text("Mots et expressions à ne jamais utiliser")
    brand_vocabulary = fields.Text("Mots et expressions à toujours utiliser")
    existing_tagline = fields.Char("Slogan existant (si applicable)")

    primary_objective = fields.Selection(
        [
            ("awareness", "Notoriété"),
            ("traffic", "Trafic web"),
            ("leads", "Génération de leads"),
            ("sales", "Ventes directes"),
            ("retention", "Fidélisation"),
            ("app_installs", "Installations d'app"),
        ],
    )
    monthly_budget_eur = fields.Float("Budget publicitaire mensuel (€)")
    target_cpa_eur = fields.Float("CPA cible (€ / conversion)")
    target_roas = fields.Float("ROAS cible (x)")
    timeline_months = fields.Integer("Horizon temporel (mois)")

    active_channel_ids = fields.Many2many(
        "doorway.traffic.channel", string="Canaux actifs"
    )
    website_url = fields.Char("URL du site web")
    ga4_property_id = fields.Char("GA4 Property ID")
    meta_page_id = fields.Char(
        string="ID page Facebook (portefeuille)",
        help="Identifiant page Meta liée à ce portefeuille.",
    )
    meta_account_id = fields.Char("Meta Ads Account ID")
    google_account_id = fields.Char("Google Ads Account ID")
    tiktok_account_id = fields.Char("TikTok Ads Account ID")
    best_performing_content = fields.Text("Contenus qui ont bien fonctionné")
    worst_performing_content = fields.Text("Contenus qui n'ont pas fonctionné")

    differentiator = fields.Text("Différenciateur généré par IA", readonly=True)
    brand_strategy = fields.Text("Stratégie générée par IA", readonly=True)
    tracking_method = fields.Text("Méthode de suivi générée par IA", readonly=True)
    brand_voice_guide = fields.Text("Guide de voix de marque généré", readonly=True)
    suggested_kpis = fields.Text("KPIs suggérés par IA", readonly=True)

    campaign_ids = fields.One2many("doorway.traffic.campaign", "foundation_id")
    campaign_count = fields.Integer(compute="_compute_campaign_count")

    _sql_constraints = [
        (
            "meta_page_unique",
            "UNIQUE(meta_page_id)",
            "Cette page Meta est déjà liée à un portefeuille.",
        ),
    ]

    @api.depends("campaign_ids")
    def _compute_campaign_count(self):
        for rec in self:
            rec.campaign_count = len(rec.campaign_ids)

    @api.depends(
        "brand_name",
        "brand_description",
        "target_persona",
        "main_value_prop",
        "competitors",
        "competitive_advantage",
        "primary_objective",
        "monthly_budget_eur",
        "active_channel_ids",
        "price_positioning",
        "target_pain_points",
    )
    def _compute_completion_pct(self):
        checks = [
            "brand_name",
            "brand_description",
            "target_persona",
            "main_value_prop",
            "competitors",
            "competitive_advantage",
            "primary_objective",
            "monthly_budget_eur",
            "price_positioning",
            "target_pain_points",
        ]
        for rec in self:
            filled = sum(1 for f in checks if getattr(rec, f))
            if rec.active_channel_ids:
                filled += 1
            total = len(checks) + 1
            rec.completion_pct = int(100 * filled / total)

    def action_analyze(self):
        for rec in self:
            if rec.completion_pct < 80:
                raise UserError(
                    _("Complétez au moins 80 %% du questionnaire avant l'analyse IA.")
                )
            rec.state = "analyzing"
            result = self.env["doorway.traffic.claude.service"].analyze_brand(rec)
            rec.write({
                "differentiator": result.get("differentiator"),
                "brand_strategy": result.get("strategy"),
                "tracking_method": result.get("tracking"),
                "brand_voice_guide": result.get("voice_guide"),
                "suggested_kpis": result.get("kpis"),
            })
        return True

    def action_validate(self):
        for rec in self:
            if not rec.differentiator and not rec.brand_strategy:
                raise UserError(_("Lancez d'abord l'analyse IA."))
            rec.state = "validated"
        return True

    def action_reset_draft(self):
        self.write({"state": "draft"})
        return True

    @api.model
    def get_validated_for_pipeline(self, pipeline_id, meta_page_id=None):
        domain = [("pipeline_id", "=", pipeline_id), ("state", "=", "validated")]
        if meta_page_id:
            domain.append(("meta_page_id", "=", meta_page_id))
        return self.search(domain, limit=1)

    def action_import_known_portfolios(self):
        created = self.env["doorway.portfolio.knowledge"].import_all_portfolios()
        return {
            "type": "ir.actions.act_window",
            "name": _("Portefeuilles importés"),
            "res_model": "doorway.brand.foundation",
            "view_mode": "kanban,list,form",
            "domain": [("id", "in", created.ids)],
        }

    def action_view_campaigns(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Campagnes — %s") % self.brand_name,
            "res_model": "doorway.traffic.campaign",
            "view_mode": "kanban,list,form",
            "domain": [("foundation_id", "=", self.id)],
            "context": {"default_foundation_id": self.id},
        }

    def action_resolve_meta_ad_account(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for rec in self:
            act_id = Ads._resolve_meta_ad_account(rec)
            rec.message_post(
                body=_("Compte Meta Ads résolu : %s") % act_id
            )
        return True

    def action_fix_meta_and_optimize(self):
        results = self.env["doorway.traffic.ads.service"].fix_meta_campaign_links(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Campagnes optimisées"),
            "res_model": "doorway.traffic.campaign",
            "view_mode": "kanban,list,form",
            "domain": [("foundation_id", "in", self.ids)],
            "context": {"search_default_filter_needs_action": 1},
        }

    def action_bootstrap_campaigns(self):
        created = self.env["doorway.portfolio.knowledge"].bootstrap_campaigns_from_portfolios()
        return {
            "type": "ir.actions.act_window",
            "name": _("Campagnes créées"),
            "res_model": "doorway.traffic.campaign",
            "view_mode": "kanban,list,form",
            "domain": [("id", "in", created.ids)],
        }
