# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mail import html2plaintext

ZONE_BENCHMARKS = {
    "canada": (15.0, "CAD"),
    "europe": (15.0, "EUR"),
    "maroc": (1.0, "USD"),
}

FOUNDATION_ZONE_MAP = {
    "canada": "canada",
    "maroc": "maroc",
    "france": "europe",
    "national": "europe",
    "local": "canada",
    "international": "europe",
}


class DoorwayTrafficCampaign(models.Model):
    _name = "doorway.traffic.campaign"
    _description = "Campagne Traffic Manager"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(required=True, tracking=True)
    foundation_id = fields.Many2one(
        "doorway.brand.foundation",
        required=True,
        string="Fondation de marque",
        ondelete="restrict",
    )
    pipeline_id = fields.Many2one(
        "crm.team", related="foundation_id.pipeline_id", store=True, readonly=True
    )
    channel_id = fields.Many2one("doorway.traffic.channel", string="Canal publicitaire")

    zone = fields.Selection(
        [
            ("canada", "🇨🇦 Canada"),
            ("europe", "🇪🇺 Europe"),
            ("maroc", "🇲🇦 Maroc"),
        ],
        string="Zone",
        tracking=True,
    )
    target_cpa_currency = fields.Char(
        string="Devise CPA",
        compute="_compute_zone_cpa",
        store=True,
    )
    effective_target_cpa = fields.Float(
        string="CPA objectif effectif",
        compute="_compute_effective_target_cpa",
        store=True,
    )
    cpa_status = fields.Selection(
        [
            ("good", "Bon"),
            ("warning", "Attention"),
            ("bad", "Critique"),
            ("neutral", "Neutre"),
        ],
        compute="_compute_cpa_status",
        store=True,
    )
    cpa_alert_level = fields.Selection(
        [
            ("urgent", "Urgent"),
            ("warning", "Attention"),
            ("none", "Aucune"),
        ],
        compute="_compute_cpa_status",
        store=True,
    )
    ai_urgency = fields.Integer(
        string="Urgence IA",
        compute="_compute_ai_urgency",
        store=True,
    )
    leads_count = fields.Integer(
        string="Leads",
        related="conversions",
        readonly=True,
    )
    reco_ids = fields.One2many(
        "doorway.traffic.campaign.reco", "campaign_id", string="Recommandations IA"
    )

    objective = fields.Selection(
        [
            ("awareness", "Notoriété"),
            ("traffic", "Trafic"),
            ("leads", "Leads"),
            ("sales", "Ventes"),
        ],
        tracking=True,
    )

    budget_total = fields.Float("Budget total (€)")
    budget_daily = fields.Float("Budget journalier (€)")
    date_start = fields.Date()
    date_end = fields.Date()

    audience_ids = fields.One2many("doorway.audience", "campaign_id")
    creative_ids = fields.One2many("doorway.creative", "campaign_id")
    placement_ids = fields.One2many("doorway.placement", "campaign_id")

    impressions = fields.Integer(readonly=True)
    clicks = fields.Integer(readonly=True)
    ctr = fields.Float("CTR %", readonly=True)
    conversions = fields.Integer(readonly=True)
    cpa = fields.Float("CPA €", readonly=True)
    roas = fields.Float("ROAS", readonly=True)
    spend = fields.Float("Dépense 7j €", readonly=True)
    spend_30d = fields.Float("Dépense 30j €", readonly=True)
    impressions_30d = fields.Integer("Impressions 30j", readonly=True)
    clicks_30d = fields.Integer("Clics 30j", readonly=True)
    ctr_30d = fields.Float("CTR 30j %", readonly=True)
    conversions_30d = fields.Integer("Conversions 30j", readonly=True)
    cpa_30d = fields.Float("CPA 30j €", readonly=True)
    meta_campaigns_matched = fields.Text(
        "Campagnes Meta agrégées",
        readonly=True,
        help="Liste JSON des campagnes Meta incluses dans les totaux.",
    )

    external_campaign_id = fields.Char(
        string="ID campagne plateforme",
        tracking=True,
        help="Identifiant Meta / Google / TikTok après publication ou liaison manuelle.",
    )
    last_sync_at = fields.Datetime("Dernière sync", readonly=True)
    sync_message = fields.Char("Message sync", readonly=True)
    meta_campaign_name = fields.Char("Nom campagne Meta", readonly=True)

    target_cpa = fields.Float(
        string="CPA objectif zone",
        compute="_compute_zone_cpa",
        store=True,
        readonly=True,
    )
    cpa_variance_pct = fields.Float(
        string="Écart CPA %",
        compute="_compute_optimization_metrics",
        store=True,
    )
    spend_pacing_pct = fields.Float(
        string="Pacing budget 7j %",
        compute="_compute_optimization_metrics",
        store=True,
        help="Dépense 7j vs budget hebdomadaire estimé (mensuel / 4.33).",
    )
    optimization_health = fields.Selection(
        [
            ("excellent", "Excellent"),
            ("good", "Bon"),
            ("warning", "Attention"),
            ("critical", "Critique"),
            ("inactive", "Inactif"),
            ("unlinked", "Non lié"),
        ],
        string="Santé perf.",
        default="good",
        tracking=True,
    )
    optimization_summary = fields.Char(
        string="Résumé optimisation",
        readonly=True,
    )
    optimization_brief = fields.Text(
        string="Brief optimisation",
        tracking=True,
        help="Vos instructions pour l'IA (angle créatif, contraintes, ton). "
        "Utilisé lors de la génération des suggestions créatifs.",
    )
    optimization_target_cpa = fields.Float(
        string="CPA cible (override)",
        tracking=True,
        help="Laissez vide pour utiliser le CPA cible de la fondation de marque.",
    )
    foundation_monthly_budget = fields.Float(
        related="foundation_id.monthly_budget_eur",
        string="Budget mensuel fondation",
        readonly=True,
    )
    optimization_monthly_budget = fields.Float(
        string="Budget mensuel cible (override)",
        tracking=True,
        help="Budget mensuel réajusté pour cette campagne (validation humaine).",
    )
    optimization_budget_daily = fields.Float(
        string="Budget journalier cible (override)",
        tracking=True,
        help="Budget journalier cible avant application sur Meta.",
    )
    budget_adjustment_notes = fields.Text(
        string="Notes réajustement budget",
        tracking=True,
    )
    optimization_customized = fields.Boolean(
        string="Optimisation personnalisée",
        default=False,
        help="Si coché, les recalculs auto ne remplacent plus l'action ni la recommandation.",
    )
    human_analysis = fields.Html(
        string="Analyse humaine",
        sanitize_attributes=False,
        help="Observations de l'expert media buyer : constats, hypothèses, décisions.",
    )
    strategy_adjustment_notes = fields.Text(
        string="Réajustement stratégie (notes)",
        tracking=True,
        help="Ce que vous voulez changer dans la stratégie : budget, angles, ciblage, priorités.",
    )
    strategy_adjusted = fields.Html(
        string="Stratégie réajustée",
        sanitize_attributes=False,
        help="Stratégie consolidée après analyse humaine + données IA.",
    )
    strategy_action_plan = fields.Text(
        string="Plan d'action stratégique",
        readonly=True,
    )
    strategy_adjusted_at = fields.Datetime(
        string="Stratégie réajustée le",
        readonly=True,
    )
    strategy_adjusted_by = fields.Many2one(
        "res.users",
        string="Réajustée par",
        readonly=True,
    )
    creative_brand_analysis = fields.Html(
        string="Analyse marque & créatifs",
        sanitize_attributes=False,
        help="Diagnostic IA : marque, offre, performance et angles créatifs recommandés.",
    )
    creative_angles_suggested = fields.Text(
        string="Angles créatifs suggérés",
        readonly=True,
    )
    targeting_strategy_analysis = fields.Html(
        string="Analyse ciblage (audiences + remarketing + placements)",
        sanitize_attributes=False,
    )
    brand_value_prop = fields.Text(
        related="foundation_id.main_value_prop",
        string="Proposition de valeur",
        readonly=True,
    )
    brand_differentiator = fields.Text(
        related="foundation_id.differentiator",
        string="Différenciateur",
        readonly=True,
    )
    brand_strategy = fields.Text(
        related="foundation_id.brand_strategy",
        string="Stratégie marque",
        readonly=True,
    )
    brand_competitive_advantage = fields.Text(
        related="foundation_id.competitive_advantage",
        string="Avantage concurrentiel",
        readonly=True,
    )
    brand_voice_guide = fields.Text(
        related="foundation_id.brand_voice_guide",
        string="Guide de voix",
        readonly=True,
    )
    brand_best_content = fields.Text(
        related="foundation_id.best_performing_content",
        string="Contenus performants",
        readonly=True,
    )
    brand_worst_content = fields.Text(
        related="foundation_id.worst_performing_content",
        string="Contenus à éviter",
        readonly=True,
    )
    brand_persona = fields.Text(
        related="foundation_id.target_persona",
        string="Persona cible",
        readonly=True,
    )

    ai_status = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("ai_proposed", "Proposition IA — en attente"),
            ("approved", "Approuvé"),
            ("active", "Active"),
            ("paused", "En pause"),
            ("ended", "Terminée"),
        ],
        default="draft",
        tracking=True,
    )
    ai_recommendation = fields.Text("Dernière recommandation IA", readonly=True)
    ai_action_pending = fields.Selection(
        [
            ("none", "Aucune"),
            ("scale_up", "Augmenter le budget"),
            ("scale_down", "Réduire le budget"),
            ("pause", "Mettre en pause"),
            ("new_audience", "Tester nouvelle audience"),
            ("new_creative", "Tester nouveau créatif"),
            ("fix_link", "Corriger lien Meta"),
        ],
        default="none",
        tracking=True,
    )
    pending_audience_count = fields.Integer(compute="_compute_pending_counts")
    pending_remarketing_count = fields.Integer(compute="_compute_pending_counts")
    pending_placement_count = fields.Integer(compute="_compute_pending_counts")
    pending_creative_count = fields.Integer(compute="_compute_pending_counts")

    @api.depends("zone")
    def _compute_zone_cpa(self):
        for rec in self:
            val, cur = ZONE_BENCHMARKS.get(rec.zone or "europe", (15.0, "EUR"))
            rec.target_cpa = val
            rec.target_cpa_currency = cur

    def _default_zone_from_foundation(self, foundation):
        if not foundation:
            return "europe"
        return FOUNDATION_ZONE_MAP.get(foundation.geographic_zone, "europe")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("zone") and vals.get("foundation_id"):
                foundation = self.env["doorway.brand.foundation"].browse(
                    vals["foundation_id"]
                )
                vals["zone"] = self._default_zone_from_foundation(foundation)
        return super().create(vals_list)

    @api.depends("target_cpa", "optimization_target_cpa", "foundation_id.target_cpa_eur")
    def _compute_effective_target_cpa(self):
        for rec in self:
            rec.effective_target_cpa = (
                rec.optimization_target_cpa
                or rec.target_cpa
                or rec.foundation_id.target_cpa_eur
                or 0.0
            )

    @api.depends("cpa", "effective_target_cpa")
    def _compute_cpa_status(self):
        for rec in self:
            target = rec.effective_target_cpa
            cpa = rec.cpa or 0
            if not target or not cpa:
                rec.cpa_status = "neutral"
                rec.cpa_alert_level = "none"
                continue
            ratio = cpa / target
            if ratio <= 0.80:
                rec.cpa_status = "good"
            elif ratio <= 1.00:
                rec.cpa_status = "warning"
            else:
                rec.cpa_status = "bad"
            if ratio > 1.00:
                rec.cpa_alert_level = "urgent"
            elif ratio > 0.80:
                rec.cpa_alert_level = "warning"
            else:
                rec.cpa_alert_level = "none"

    @api.depends("cpa_alert_level", "ai_action_pending", "cpa_status")
    def _compute_ai_urgency(self):
        action_rank = {
            "pause": 90,
            "scale_down": 80,
            "fix_link": 70,
            "new_creative": 60,
            "new_audience": 50,
            "scale_up": 40,
            "none": 0,
        }
        alert_rank = {"urgent": 100, "warning": 50, "none": 0}
        for rec in self:
            rec.ai_urgency = (
                alert_rank.get(rec.cpa_alert_level, 0)
                + action_rank.get(rec.ai_action_pending, 0)
            )

    @api.depends(
        "cpa",
        "effective_target_cpa",
        "spend",
        "foundation_id.monthly_budget_eur",
        "optimization_monthly_budget",
    )
    def _compute_optimization_metrics(self):
        for rec in self:
            target = rec.effective_target_cpa or 0
            if target and rec.cpa:
                rec.cpa_variance_pct = round(
                    100.0 * (rec.cpa - target) / target, 1
                )
            else:
                rec.cpa_variance_pct = 0.0
            monthly = (
                rec.optimization_monthly_budget
                or rec.foundation_id.monthly_budget_eur
                or 0
            )
            weekly_budget = monthly / 4.33
            rec.spend_pacing_pct = (
                round(100.0 * (rec.spend or 0) / weekly_budget, 1)
                if weekly_budget
                else 0.0
            )

    @api.depends(
        "audience_ids.ai_status",
        "audience_ids.audience_type",
        "creative_ids.ai_status",
        "placement_ids.ai_status",
    )
    def _compute_pending_counts(self):
        for rec in self:
            proposed_aud = rec.audience_ids.filtered(
                lambda a: a.ai_status == "proposed"
            )
            rec.pending_audience_count = len(
                proposed_aud.filtered(
                    lambda a: a.audience_type != "retargeting"
                )
            )
            rec.pending_remarketing_count = len(
                proposed_aud.filtered(
                    lambda a: a.audience_type == "retargeting"
                )
            )
            rec.pending_placement_count = len(
                rec.placement_ids.filtered(lambda p: p.ai_status == "proposed")
            )
            rec.pending_creative_count = len(
                rec.creative_ids.filtered(lambda c: c.ai_status == "proposed")
            )

    @api.constrains("foundation_id")
    def _check_foundation_validated(self):
        for rec in self:
            if rec.foundation_id.state != "validated":
                raise UserError(
                    _(
                        "La fondation de marque « %s » doit être validée avant "
                        "de créer une campagne."
                    )
                    % rec.foundation_id.brand_name
                )

    def action_generate_with_ai(self):
        Claude = self.env["doorway.traffic.claude.service"]
        Audience = self.env["doorway.audience"]
        Creative = self.env["doorway.creative"]
        for campaign in self:
            foundation = campaign.foundation_id
            result = Claude.generate_campaign(campaign, foundation)
            for aud in result.get("audiences", []):
                targeting = aud.get("targeting") or {}
                Audience.create({
                    "campaign_id": campaign.id,
                    "name": aud.get("name") or "Audience IA",
                    "description": aud.get("description"),
                    "audience_type": aud.get("audience_type") or "cold",
                    "platform": aud.get("platform") or (
                        campaign.channel_id.code if campaign.channel_id else "meta"
                    ),
                    "targeting": json.dumps(targeting, ensure_ascii=False),
                    "estimated_size": aud.get("estimated_size") or 0,
                    "source": "ai_generated",
                    "ai_status": "proposed",
                })
            for creative in result.get("creatives", []):
                Creative.create({
                    "campaign_id": campaign.id,
                    "format": creative.get("format") or "image",
                    "headline": creative.get("headline"),
                    "body": creative.get("body"),
                    "cta": creative.get("cta"),
                    "ai_status": "proposed",
                })
            campaign.write({
                "ai_recommendation": result.get("strategy_notes"),
                "ai_status": "ai_proposed",
            })
        return True

    def action_approve(self):
        self.write({"ai_status": "approved"})
        return True

    def action_activate(self):
        self.write({"ai_status": "active"})
        return True

    def action_pause(self):
        self.write({"ai_status": "paused", "ai_action_pending": "none"})
        return True

    def action_apply_ai_recommendation(self):
        for campaign in self:
            action = campaign.ai_action_pending
            if action == "scale_up":
                campaign.budget_daily = (campaign.budget_daily or 0) * 1.25
            elif action == "scale_down":
                campaign.budget_daily = (campaign.budget_daily or 0) * 0.75
            elif action == "pause":
                campaign.ai_status = "paused"
            elif action == "fix_link":
                self.env["doorway.traffic.ads.service"].fix_meta_campaign_links(
                    campaign.foundation_id
                )
            elif action == "new_audience":
                self.env["doorway.traffic.ads.service"].suggest_targeting(
                    campaign, force=True
                )
            elif action == "new_creative":
                self.env["doorway.traffic.ads.service"].suggest_creatives(campaign)
            campaign.write({"ai_action_pending": "none"})
            self.env["doorway.traffic.optimizer.rules"].apply_to_campaign(campaign)
        return True

    def action_analyze_optimization(self):
        Rules = self.env["doorway.traffic.optimizer.rules"]
        for campaign in self:
            Rules.apply_to_campaign(campaign)
        return True

    def action_sync_and_optimize(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            try:
                Ads.sync_campaign_performance(campaign)
            except UserError as exc:
                campaign.sync_message = str(exc)
            Ads._post_sync_optimize(campaign)
        return True

    def _mark_optimization_customized(self, vals):
        keys = (
            "optimization_brief",
            "ai_action_pending",
            "optimization_target_cpa",
            "optimization_monthly_budget",
            "optimization_budget_daily",
            "budget_adjustment_notes",
            "human_analysis",
            "strategy_adjustment_notes",
            "strategy_adjusted",
        )
        if any(k in vals for k in keys):
            vals["optimization_customized"] = True
        return vals

    def write(self, vals):
        return super().write(self._mark_optimization_customized(vals))

    def action_suggest_creatives(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            Ads.suggest_creatives(campaign)
        return True

    def action_analyze_brand_creatives(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            Ads.analyze_brand_creatives(campaign)
        return True

    def action_analyze_targeting_strategy(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            Ads.analyze_targeting_strategy(campaign)
        return True

    def action_regenerate_targeting_suggestions(self):
        """Régénère audiences, remarketing et placements selon marque + perf."""
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            if not campaign.targeting_strategy_analysis:
                Ads.analyze_targeting_strategy(campaign)
            Ads.suggest_targeting(campaign, force=True)
        return True

    def action_regenerate_creative_suggestions(self):
        """Analyse marque/offre puis régénère les créatifs selon le brief utilisateur."""
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            if not campaign.creative_brand_analysis:
                Ads.analyze_brand_creatives(campaign)
            Ads.suggest_creatives(campaign, force=True)
        return True

    def action_synthesize_human_strategy(self):
        """Synthétise analyse humaine + données auto en stratégie réajustée."""
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            if not campaign.human_analysis and not campaign.strategy_adjustment_notes:
                raise UserError(
                    _(
                        "Renseignez l'analyse humaine ou les notes de réajustement "
                        "avant de synthétiser la stratégie."
                    )
                )
            Ads.synthesize_strategy_adjustment(campaign)
        return True

    def action_apply_budget_targets(self):
        """Applique CPA cible + budgets réajustés (validation humaine)."""
        for campaign in self:
            vals = {}
            foundation_vals = {}
            if campaign.optimization_budget_daily:
                vals["budget_daily"] = campaign.optimization_budget_daily
            if campaign.optimization_monthly_budget:
                vals["budget_total"] = campaign.optimization_monthly_budget
            if campaign.optimization_target_cpa:
                foundation_vals["target_cpa_eur"] = campaign.optimization_target_cpa
            if not vals and not foundation_vals:
                raise UserError(
                    _(
                        "Renseignez au moins un élément : CPA cible, budget "
                        "journalier ou budget mensuel."
                    )
                )
            if vals:
                campaign.write(vals)
            if foundation_vals:
                campaign.foundation_id.sudo().write(foundation_vals)
            note = campaign.budget_adjustment_notes or ""
            parts = []
            if campaign.optimization_target_cpa:
                parts.append(_("CPA cible : %s €") % campaign.optimization_target_cpa)
            if vals.get("budget_daily"):
                parts.append(_("Budget journalier : %s €") % vals["budget_daily"])
            if vals.get("budget_total"):
                parts.append(_("Budget mensuel : %s €") % vals["budget_total"])
            campaign.message_post(
                body=_("Paramètres appliqués — %s. %s")
                % (" · ".join(parts), note)
            )
            campaign.write({"optimization_customized": True})
        return True

    def action_apply_human_strategy_realignment(self):
        """Applique la stratégie réajustée et relance toutes les suggestions IA."""
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            if not campaign.strategy_adjusted:
                Ads.synthesize_strategy_adjustment(campaign)
            Ads.apply_human_strategy_realignment(campaign)
        return True

    def action_reset_optimization(self):
        """Réinitialise la personnalisation et recalcule depuis les règles."""
        Rules = self.env["doorway.traffic.optimizer.rules"]
        self.write({
            "optimization_customized": False,
            "optimization_brief": False,
            "optimization_target_cpa": 0,
            "optimization_monthly_budget": 0,
            "optimization_budget_daily": 0,
            "budget_adjustment_notes": False,
            "human_analysis": False,
            "strategy_adjustment_notes": False,
            "strategy_adjusted": False,
            "strategy_action_plan": False,
            "strategy_adjusted_at": False,
            "strategy_adjusted_by": False,
        })
        for campaign in self:
            Rules.apply_to_campaign(campaign)
        return True

    def action_ignore_recommendation(self):
        self.write({"ai_action_pending": "none", "ai_recommendation": ""})
        return True

    def action_sync_insights(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            Ads.sync_campaign_performance(campaign)
        return True

    def action_publish_to_ads(self):
        Ads = self.env["doorway.traffic.ads.service"]
        for campaign in self:
            Ads.publish_campaign(campaign)
        return True

    # ── Handlers recommandations ─────────────────────────────────────────

    def _reco_apply_scale_up(self):
        self.budget_daily = (self.budget_daily or 0) * 1.25

    def _reco_apply_scale_down(self):
        self.budget_daily = (self.budget_daily or 0) * 0.75

    def _reco_apply_pause(self):
        self.ai_status = "paused"

    def _reco_apply_new_audience(self):
        self.env["doorway.traffic.ads.service"].suggest_targeting(self, force=True)

    def _reco_apply_new_creative(self):
        self.env["doorway.traffic.ads.service"].suggest_creatives(self, force=True)

    def _reco_apply_fix_link(self):
        self.env["doorway.traffic.ads.service"].fix_meta_campaign_links(
            self.foundation_id
        )

    def _ensure_reco_from_pending(self):
        """Convertit ai_action_pending en reco inbox si absent."""
        Reco = self.env["doorway.traffic.campaign.reco"]
        action_labels = dict(self._fields["ai_action_pending"].selection)
        urgency_map = {
            "scale_down": "urgent",
            "pause": "urgent",
            "fix_link": "urgent",
            "new_creative": "info",
            "new_audience": "info",
            "scale_up": "opportunity",
        }
        for campaign in self:
            if campaign.ai_action_pending == "none":
                continue
            existing = Reco.search([
                ("campaign_id", "=", campaign.id),
                ("state", "=", "pending"),
            ], limit=1)
            if existing:
                continue
            action = campaign.ai_action_pending
            urgency = urgency_map.get(action, "info")
            if campaign.cpa_alert_level == "urgent":
                urgency = "urgent"
            elif campaign.cpa_status == "good" and action == "scale_up":
                urgency = "opportunity"
            Reco.create({
                "campaign_id": campaign.id,
                "title": action_labels.get(action, action),
                "body": campaign.ai_recommendation or campaign.optimization_summary,
                "action_type": action if action != "none" else "info",
                "urgency": urgency,
                "confidence": 85,
            })

    @api.model
    def cron_check_cpa_alerts(self):
        """Cron 24h — crée des recommandations si CPA > 80% objectif."""
        campaigns = self.search([
            ("ai_status", "=", "active"),
            ("cpa", ">", 0),
        ])
        Reco = self.env["doorway.traffic.campaign.reco"]
        action_labels = dict(self._fields["ai_action_pending"].selection)
        for campaign in campaigns:
            alert = campaign.cpa_alert_level
            if alert == "none":
                continue
            existing = Reco.search([
                ("campaign_id", "=", campaign.id),
                ("state", "=", "pending"),
                ("action_type", "in", ["scale_down", "new_audience", "new_creative"]),
            ], limit=1)
            if existing:
                continue
            action = campaign.ai_action_pending
            if action == "none":
                if alert == "urgent":
                    action = "new_creative"
                else:
                    action = "scale_up" if campaign.cpa_status == "good" else "new_audience"
            Reco.create({
                "campaign_id": campaign.id,
                "title": action_labels.get(action, "Optimiser la campagne"),
                "body": (
                    f"CPA {campaign.cpa:.2f} {campaign.target_cpa_currency} "
                    f"vs objectif {campaign.effective_target_cpa:.2f} "
                    f"{campaign.target_cpa_currency}. "
                    f"{campaign.optimization_summary or ''}"
                ),
                "action_type": action,
                "urgency": "urgent" if alert == "urgent" else "opportunity",
                "confidence": 88,
            })
            if alert in ("urgent", "warning"):
                campaign.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_(
                        "CPA %(cpa).2f vs objectif %(target).2f %(cur)s — %(name)s"
                    ) % {
                        "cpa": campaign.cpa,
                        "target": campaign.effective_target_cpa,
                        "cur": campaign.target_cpa_currency,
                        "name": campaign.name,
                    },
                )

    # ── API dashboard OWL ────────────────────────────────────────────────

    @api.model
    def get_dashboard_stats(self):
        campaigns = self.search([("ai_status", "in", ("active", "approved", "ai_proposed"))])
        active = campaigns.filtered(lambda c: c.ai_status == "active")
        monthly_budget = sum(
            c.optimization_monthly_budget or c.foundation_id.monthly_budget_eur or 0
            for c in active
        )
        leads_month = sum(c.conversions_30d or 0 for c in active)
        cpas = [c.cpa for c in active if c.cpa]
        avg_cpa = round(sum(cpas) / len(cpas), 2) if cpas else 0
        pending_recos = self.env["doorway.traffic.campaign.reco"].search_count([
            ("state", "=", "pending"),
        ])
        alert_count = len(active.filtered(
            lambda c: c.cpa_alert_level in ("urgent", "warning")
            or c.ai_action_pending != "none"
        ))
        return {
            "active_count": len(active),
            "monthly_budget": round(monthly_budget, 2),
            "leads_month": leads_month,
            "avg_cpa": avg_cpa,
            "alert_count": alert_count,
            "pending_recos": pending_recos,
            "benchmarks": {
                "canada": {"target": 15, "currency": "CAD", "label": "🇨🇦 Canada"},
                "europe": {"target": 15, "currency": "EUR", "label": "🇪🇺 Europe"},
                "maroc": {"target": 1, "currency": "USD", "label": "🇲🇦 Maroc"},
            },
        }

    @api.model
    def get_dashboard_alerts(self, limit=20):
        self.search([])._ensure_reco_from_pending()
        campaigns = self.search([
            "|",
            ("ai_action_pending", "!=", "none"),
            ("cpa_alert_level", "in", ["urgent", "warning"]),
            ("ai_status", "in", ("active", "approved")),
        ], order="ai_urgency desc", limit=limit)
        action_labels = dict(self._fields["ai_action_pending"].selection)
        status_labels = dict(self._fields["cpa_status"].selection)
        rows = []
        for c in campaigns:
            rows.append({
                "id": c.id,
                "name": c.name,
                "zone": c.zone,
                "zone_label": dict(c._fields["zone"].selection).get(c.zone, ""),
                "channel": c.channel_id.name or "—",
                "cpa": c.cpa,
                "target_cpa": c.effective_target_cpa,
                "currency": c.target_cpa_currency,
                "cpa_status": c.cpa_status,
                "cpa_status_label": status_labels.get(c.cpa_status, ""),
                "action": c.ai_action_pending,
                "action_label": action_labels.get(c.ai_action_pending, ""),
                "recommendation": html2plaintext(
                    c.ai_recommendation or c.optimization_summary or ""
                ).strip(),
                "urgency": c.cpa_alert_level if c.cpa_alert_level != "none" else (
                    "opportunity" if c.cpa_status == "good" else "info"
                ),
            })
        return rows

    @api.model
    def dashboard_list_campaigns(self, filters=None, zone=None, status=None):
        filters = dict(filters or {})
        # Compat : ancien JS passait zone/status comme kwargs séparés
        if zone:
            filters["zone"] = zone
        if status:
            filters["status"] = status
        domain = []
        if filters.get("zone"):
            domain.append(("zone", "=", filters["zone"]))
        if filters.get("status") == "active":
            domain.append(("ai_status", "=", "active"))
        elif filters.get("status") == "paused":
            domain.append(("ai_status", "=", "paused"))
        elif filters.get("status") == "alerts":
            domain.extend([
                "|",
                ("ai_action_pending", "!=", "none"),
                ("cpa_alert_level", "in", ["urgent", "warning"]),
            ])
        campaigns = self.search(domain, order="ai_urgency desc, name")
        campaigns._ensure_reco_from_pending()
        status_labels = dict(self._fields["ai_status"].selection)
        zone_labels = dict(self._fields["zone"].selection)
        return {
            "campaigns": [{
                "id": c.id,
                "name": c.name,
                "zone": c.zone,
                "zone_label": zone_labels.get(c.zone, ""),
                "channel": c.channel_id.name or "—",
                "channel_code": c.channel_id.code or "",
                "cpa": c.cpa,
                "target_cpa": c.effective_target_cpa,
                "currency": c.target_cpa_currency,
                "cpa_status": c.cpa_status,
                "status": c.ai_status,
                "status_label": status_labels.get(c.ai_status, ""),
                "leads": c.conversions or 0,
                "spend": c.spend or 0,
                "action_pending": c.ai_action_pending,
                "recommendation": html2plaintext(
                    c.ai_recommendation or ""
                ).strip(),
            } for c in campaigns],
            "zones": [
                {"value": k, "label": v}
                for k, v in self._fields["zone"].selection
            ],
        }

    def dashboard_campaign_detail(self):
        self.ensure_one()
        self._ensure_reco_from_pending()
        Reco = self.env["doorway.traffic.campaign.reco"]
        recos = Reco.search_read(
            [("campaign_id", "=", self.id), ("state", "=", "pending")],
            ["title", "body", "action_type", "urgency", "confidence", "state"],
        )
        creatives = self.env["doorway.creative"].search_read(
            [("campaign_id", "=", self.id), ("ai_status", "in", ("proposed", "approved"))],
            ["headline", "format", "ai_status", "media_status", "preview_image"],
            limit=12,
        )
        audiences = self.env["doorway.audience"].search_read(
            [("campaign_id", "=", self.id), ("ai_status", "=", "proposed")],
            ["name", "audience_type", "targeting_rationale"],
            limit=12,
        )
        zone_labels = dict(self._fields["zone"].selection)
        return {
            "campaign": {
                "id": self.id,
                "name": self.name,
                "zone": self.zone,
                "zone_label": zone_labels.get(self.zone, ""),
                "channel": self.channel_id.name or "—",
                "cpa": self.cpa,
                "target_cpa": self.effective_target_cpa,
                "currency": self.target_cpa_currency,
                "cpa_status": self.cpa_status,
                "budget_daily": self.budget_daily,
                "leads": self.conversions,
                "spend": self.spend,
                "spend_30d": self.spend_30d,
                "recommendation": self.ai_recommendation or "",
                "analysis": self.creative_brand_analysis or self.human_analysis or "",
                "status": self.ai_status,
            },
            "recos": recos,
            "creatives": creatives,
            "audiences": audiences,
        }

    def action_analyze_with_ai(self):
        self.env["doorway.traffic.ads.service"].analyze_brand_creatives(self)
        self.env["doorway.traffic.ads.service"].analyze_targeting_strategy(self)
        self.env["doorway.traffic.optimizer.rules"].apply_to_campaign(self)
        return self.dashboard_campaign_detail()

    def action_suggest_audience(self):
        self.env["doorway.traffic.ads.service"].suggest_targeting(self, force=True)
        return True

    def action_generate_canva_creative(self):
        creative = self.creative_ids.filtered(
            lambda c: c.format not in ("video", "reel", "story")
        )[:1]
        if not creative:
            self.env["doorway.traffic.ads.service"].suggest_creatives(self, force=True)
            creative = self.creative_ids.filtered(
                lambda c: c.format not in ("video", "reel", "story")
            )[:1]
        if creative:
            return creative.action_generate_canva_design()
        return {
            "status": "skipped",
            "message": _("Aucun créatif image — générez d'abord des propositions IA."),
        }

    def action_generate_heygen_video(self):
        creative = self.creative_ids.filtered(
            lambda c: c.format in ("video", "reel", "story")
        )[:1]
        if not creative:
            self.env["doorway.traffic.ads.service"].suggest_creatives(self, force=True)
            creative = self.creative_ids.filtered(
                lambda c: c.format in ("video", "reel", "story")
            )[:1]
        if creative:
            creative.action_generate_video()
        return True

    @api.model
    def backfill_zones(self):
        for campaign in self.search([("zone", "=", False)]):
            campaign.zone = campaign._default_zone_from_foundation(campaign.foundation_id)
