# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.doorway_traffic_manager.services.ad_connectors.meta_connector import (
    MetaAdsConnector,
)
from odoo.addons.doorway_traffic_manager.services.ad_connectors.google_connector import (
    GoogleAdsConnector,
)
from odoo.addons.doorway_traffic_manager.services.ad_connectors.tiktok_connector import (
    TikTokAdsConnector,
)
from odoo.addons.doorway_traffic_manager.services.analytics.ga4_connector import (
    GA4Connector,
)

_logger = logging.getLogger(__name__)

OBJECTIVE_META_MAP = {
    "awareness": "OUTCOME_AWARENESS",
    "traffic": "OUTCOME_TRAFFIC",
    "leads": "OUTCOME_LEADS",
    "sales": "OUTCOME_SALES",
}

# Liens validés portefeuille → campagne Meta ACTIVE (corrigés manuellement)
PORTFOLIO_META_CAMPAIGN_IDS = {
    "Maison Recherchée": ("120245070455380396", "Maison Recherchee"),
    "ICI Thermopompe": ("120245419811370396", "Thermopompe 12 avril"),
    "Haidly Rénovation": (
        "120233396876420396",
        "Campagne Acquisition de Prospects - ISOLATION DE GRENIER - S3",
    ),
    "Énergie Pro": (
        "120233396994270396",
        "Campagne Acquisition Traffic - ISOLATION DE GRENIER - S3",
    ),
    "Agence Doorway": (False, False),  # pas de campagne marketing ACTIVE
}

# Mots-clés fallback si ID explicite absent
PORTFOLIO_META_KEYWORDS = {
    "Agence Doorway": ["doorway", "marketing", "recrutement b2b", "recrutement campagne"],
    "Maison Recherchée": ["maison recherche", "maison recherch"],
    "Haidly Rénovation": ["haidly", "haidly smile"],
    "ICI Thermopompe": ["ici thermopompe", "thermopompe 12"],
    "Énergie Pro": ["ecoenergie", "energie pro", "énergie pro", "eco-therma"],
}

# Agrégation dépenses : toutes les campagnes Meta dont le nom contient ces mots-clés
PORTFOLIO_AGGREGATE_KEYWORDS = {
    "Agence Doorway": ["doorway", "marketing", "recrutement"],
    "Maison Recherchée": ["maison recherche", "maison recherch"],
    "Haidly Rénovation": [
        "haidly",
        "isolation qc",
        "prospects - isolation de grenier",
        "prospects - toit plat",
        "prospects - peinture",
    ],
    "ICI Thermopompe": ["thermopompe", "ici thermopompe"],
    "Énergie Pro": [
        "traffic - isolation de grenier",
        "ecoenergie",
        "eco-therma",
        "energie pro",
    ],
}


class DoorwayTrafficAdsService(models.AbstractModel):
    _name = "doorway.traffic.ads.service"
    _description = "Service connecteurs publicitaires Traffic Manager"

    def _icp(self):
        return self.env["ir.config_parameter"].sudo()

    def _get_meta_token(self):
        token = (
            self._icp().get_param("doorway_traffic_manager.meta_ads_access_token")
            or ""
        ).strip()
        if not token and "doorway.veille.config" in self.env:
            cfg = self.env["doorway.veille.config"].search([], limit=1)
            token = (cfg.meta_access_token or "").strip()
        if not token:
            token = (
                self._icp().get_param("doorway_social_ia.meta_system_user_token") or ""
            ).strip()
        return token

    def _ensure_meta_token(self, connector):
        if not connector.access_token:
            raise UserError(
                _(
                    "Token Meta manquant — renouvelez-le dans "
                    "Veille sociale → Connecter tous Meta, ou configurez "
                    "doorway_traffic_manager.meta_ads_access_token."
                )
            )
        token_check = connector.validate_token()
        if not token_check["ok"]:
            msg = token_check.get("message") or ""
            if "expired" in msg.lower() or "session has expired" in msg.lower():
                raise UserError(
                    _(
                        "Token Meta expiré — reconnectez Meta dans "
                        "Veille sociale → Connecter tous Meta, puis réessayez."
                    )
                )
            raise UserError(_("Meta API : %s") % msg)

    def _resolve_meta_ad_account(self, foundation, connector=None):
        foundation.ensure_one()
        connector = connector or MetaAdsConnector(self._get_meta_token())
        self._ensure_meta_token(connector)

        account_id = (foundation.meta_account_id or "").strip()
        page_id = (foundation.meta_page_id or "").strip()
        if account_id and not MetaAdsConnector.is_placeholder_account(
            account_id, page_id
        ):
            return account_id

        if not page_id:
            raise UserError(
                _(
                    "Renseignez l'ID page Meta ou le compte Ads (act_XXXXX) "
                    "sur la fondation « %s »."
                )
                % foundation.brand_name
            )

        resolved = connector.find_ad_account_for_page(page_id)
        if not resolved["ok"]:
            raise UserError(resolved["message"])

        act_id = resolved["data"]
        foundation.sudo().write({"meta_account_id": act_id})
        if resolved.get("warning") == "fallback_single_ad_account":
            foundation.message_post(
                body=_(
                    "Compte Ads auto-sélectionné (seul compte accessible) : %s"
                )
                % (resolved.get("account_name") or act_id)
            )
        return act_id

    def _meta_connector(self, foundation):
        token = self._get_meta_token()
        connector = MetaAdsConnector(token)
        account_id = self._resolve_meta_ad_account(foundation, connector)
        connector.ad_account_id = connector._normalize_account_id(account_id)
        return connector

    def resolve_meta_ad_accounts(self, foundations=None):
        """Résout act_XXXXX pour chaque portefeuille (bouton UI / cron)."""
        foundations = foundations or self.env["doorway.brand.foundation"].search([
            ("meta_page_id", "!=", False),
        ])
        token = self._get_meta_token()
        connector = MetaAdsConnector(token)
        self._ensure_meta_token(connector)
        resolved = []
        errors = []
        for foundation in foundations:
            try:
                act_id = self._resolve_meta_ad_account(foundation, connector)
                resolved.append((foundation.brand_name, act_id))
            except UserError as exc:
                errors.append("%s : %s" % (foundation.brand_name, exc))
        if errors and not resolved:
            raise UserError("\n".join(errors))
        return resolved, errors

    @api.model
    def fix_meta_campaign_links(self, foundations=None):
        """Applique les liens Meta validés + sync 7j + règles optimisation."""
        foundations = foundations or self.env["doorway.brand.foundation"].search([
            ("state", "=", "validated"),
        ])
        Campaign = self.env["doorway.traffic.campaign"]
        Rules = self.env["doorway.traffic.optimizer.rules"]
        results = []
        for foundation in foundations:
            mapping = PORTFOLIO_META_CAMPAIGN_IDS.get(foundation.brand_name)
            campaign = Campaign.search([("foundation_id", "=", foundation.id)], limit=1)
            if not campaign:
                continue
            if mapping and mapping[0]:
                campaign.write({
                    "external_campaign_id": mapping[0],
                    "meta_campaign_name": mapping[1],
                })
            try:
                self.sync_campaign_performance(campaign)
                self._post_sync_optimize(campaign)
                results.append((
                    foundation.brand_name,
                    "ok",
                    campaign.external_campaign_id or "",
                ))
            except UserError as exc:
                campaign.sync_message = str(exc)
                self._post_sync_optimize(campaign)
                results.append((foundation.brand_name, "erreur", str(exc)))
        return results

    def _campaigns_matching_portfolio(self, foundation, meta_campaigns):
        keywords = PORTFOLIO_AGGREGATE_KEYWORDS.get(foundation.brand_name, [])
        brand_tokens = [
            t
            for t in (foundation.brand_name or "").lower()
            .replace("é", "e")
            .replace("è", "e")
            .split()
            if len(t) > 3
        ]
        keywords = keywords + brand_tokens
        matched = []
        for mc in meta_campaigns:
            name = (mc.get("name") or "").lower().replace("é", "e").replace("è", "e")
            if any(kw in name for kw in keywords):
                matched.append(mc)
        primary = PORTFOLIO_META_CAMPAIGN_IDS.get(foundation.brand_name)
        if primary and primary[0]:
            pid = str(primary[0])
            if not any(str(m.get("id")) == pid for m in matched):
                for mc in meta_campaigns:
                    if str(mc.get("id")) == pid:
                        matched.insert(0, mc)
                        break
        return matched

    def _post_sync_optimize(self, campaign):
        Rules = self.env["doorway.traffic.optimizer.rules"]
        Rules.apply_to_campaign(campaign)
        if (campaign.spend or 0) > 0 or (campaign.spend_30d or 0) > 0:
            self.analyze_brand_creatives(campaign)
            self.analyze_targeting_strategy(campaign)
        if not campaign.audience_ids.filtered(lambda a: a.ai_status == "proposed"):
            if (campaign.spend or 0) > 0 or (campaign.spend_30d or 0) > 0:
                self.suggest_targeting(campaign)
        if campaign.ai_action_pending in ("new_creative", "scale_down", "scale_up"):
            self.suggest_creatives(campaign)
        elif not campaign.creative_ids.filtered(lambda c: c.ai_status == "proposed"):
            if (campaign.spend or 0) > 0 or (campaign.spend_30d or 0) > 0:
                self.suggest_creatives(campaign)

    def _build_brand_creative_payload(self, campaign):
        campaign.ensure_one()
        foundation = campaign.foundation_id
        target_cpa = campaign.optimization_target_cpa or foundation.target_cpa_eur
        probleme_parts = [
            campaign.optimization_summary,
            campaign.ai_recommendation,
        ]
        if campaign.strategy_adjustment_notes:
            probleme_parts.insert(0, campaign.strategy_adjustment_notes)
        if campaign.optimization_brief:
            probleme_parts.insert(0, campaign.optimization_brief)
        proposed = campaign.creative_ids.filtered(lambda c: c.ai_status == "proposed")
        active = campaign.creative_ids.filtered(
            lambda c: c.ai_status in ("active", "approved", "winner")
        )
        return {
            "marque": foundation.brand_name,
            "description": foundation.brand_description,
            "offre": foundation.main_value_prop,
            "valeur": foundation.main_value_prop,
            "differentiateur": foundation.differentiator,
            "avantage_concurrentiel": foundation.competitive_advantage,
            "strategie": campaign.strategy_adjusted or foundation.brand_strategy,
            "strategie_marque": foundation.brand_strategy,
            "strategie_reajustee": campaign.strategy_adjusted or "",
            "analyse_humaine": campaign.human_analysis or "",
            "notes_reajustement": campaign.strategy_adjustment_notes or "",
            "plan_action_strategique": campaign.strategy_action_plan or "",
            "guide_voix": foundation.brand_voice_guide,
            "vocabulaire": foundation.brand_vocabulary,
            "tabous": foundation.brand_taboos,
            "slogan": foundation.existing_tagline,
            "cible": foundation.target_persona,
            "pain_points": foundation.target_pain_points,
            "desirs": foundation.target_desires,
            "ton": foundation.brand_tone_ids.mapped("name"),
            "style": foundation.communication_style,
            "contenus_performants": foundation.best_performing_content,
            "contenus_faibles": foundation.worst_performing_content,
            "probleme": " — ".join(p for p in probleme_parts if p),
            "brief_utilisateur": campaign.optimization_brief or "",
            "action": campaign.ai_action_pending,
            "cpa": campaign.cpa,
            "cpa_30d": campaign.cpa_30d,
            "cpa_cible": target_cpa,
            "ctr": campaign.ctr,
            "ctr_30d": campaign.ctr_30d,
            "spend_7j": campaign.spend,
            "spend_30j": campaign.spend_30d,
            "conversions_7j": campaign.conversions,
            "conversions_30j": campaign.conversions_30d,
            "creatifs_proposes": [
                {
                    "format": c.format,
                    "headline": c.headline,
                    "angle": c.brand_angle,
                }
                for c in proposed
            ],
            "creatifs_actifs": [
                {"format": c.format, "ctr": c.ctr, "cpa": c.cpa}
                for c in active
            ],
            "analyse_precedente": campaign.creative_angles_suggested or "",
        }

    def _format_brand_creative_analysis(self, data):
        angles = data.get("angles_creatifs") or []
        angles_html = "".join(
            "<li><b>%s</b> (%s) — %s</li>"
            % (
                a.get("angle", "?"),
                a.get("format", "?"),
                a.get("justification", ""),
            )
            for a in angles
        )
        favoriser = "".join(
            "<li>%s</li>" % x for x in (data.get("contenus_a_favoriser") or [])
        )
        eviter = "".join(
            "<li>%s</li>" % x for x in (data.get("contenus_a_eviter") or [])
        )
        return (
            "<h4>Marque</h4><p>%s</p>"
            "<h4>Offre</h4><p>%s</p>"
            "<h4>Diagnostic performance</h4><p>%s</p>"
            "<h4>À favoriser</h4><ul>%s</ul>"
            "<h4>À éviter</h4><ul>%s</ul>"
            "<h4>Angles créatifs recommandés</h4><ul>%s</ul>"
            "<h4>Recommandations</h4><p>%s</p>"
        ) % (
            data.get("marque_resume", ""),
            data.get("offre_resume", ""),
            data.get("diagnostic_perf", ""),
            favoriser or "<li>—</li>",
            eviter or "<li>—</li>",
            angles_html or "<li>—</li>",
            data.get("recommandations", ""),
        )

    def analyze_brand_creatives(self, campaign):
        """Analyse marque + offre + perf et propose des angles créatifs."""
        campaign.ensure_one()
        payload = self._build_brand_creative_payload(campaign)
        data = self.env["doorway.traffic.claude.service"].analyze_brand_creatives(
            payload
        )
        angles_text = "\n".join(
            "- %s (%s) : %s"
            % (
                a.get("angle", "?"),
                a.get("format", "?"),
                a.get("justification", ""),
            )
            for a in (data.get("angles_creatifs") or [])
        )
        campaign.write({
            "creative_brand_analysis": self._format_brand_creative_analysis(data),
            "creative_angles_suggested": angles_text,
        })
        return data

    def suggest_creatives(self, campaign, force=False):
        """Génère 2-3 créatifs proposés ancrés marque/offre (Claude + fallback)."""
        campaign.ensure_one()
        foundation = campaign.foundation_id
        Creative = self.env["doorway.creative"]
        existing = Creative.search([
            ("campaign_id", "=", campaign.id),
            ("ai_status", "=", "proposed"),
        ])
        if force and existing:
            existing.write({"ai_status": "rejected"})
            existing = Creative.browse()
        elif len(existing) >= 2:
            return existing

        if not campaign.creative_brand_analysis:
            self.analyze_brand_creatives(campaign)

        payload = self._build_brand_creative_payload(campaign)
        payload["angles_suggérés"] = campaign.creative_angles_suggested or ""

        ideas = self.env["doorway.traffic.claude.service"].suggest_creatives(
            payload
        )
        created = Creative.browse()
        for idea in ideas[:3]:
            created |= Creative.create({
                "campaign_id": campaign.id,
                "format": idea.get("format") or "image",
                "headline": idea.get("headline"),
                "body": idea.get("body"),
                "cta": idea.get("cta") or "En savoir plus",
                "brand_angle": idea.get("angle"),
                "creative_rationale": idea.get("rationale"),
                "canva_brief": idea.get("canva_brief"),
                "visual_description": idea.get("visual_description"),
                "ai_status": "proposed",
            })
        Media = self.env["doorway.traffic.media.service"]
        for cr in created:
            Media.ensure_creative_preview(cr)
            if cr.format in ("video", "reel", "story") and not cr.video_script:
                cr.video_script = cr.body or cr.headline or ""
        if created:
            campaign.message_post(
                body=_(
                    "%s créatif(s) IA proposé(s) — aperçus visuels générés."
                )
                % len(created)
            )
        return created

    def _build_targeting_payload(self, campaign):
        payload = self._build_brand_creative_payload(campaign)
        foundation = campaign.foundation_id
        payload.update({
            "age_min": foundation.target_age_min,
            "age_max": foundation.target_age_max,
            "objectif": campaign.objective,
            "canal": campaign.channel_id.code if campaign.channel_id else "meta",
            "audiences_existantes": [
                {
                    "name": a.name,
                    "type": a.audience_type,
                    "status": a.ai_status,
                }
                for a in campaign.audience_ids
            ],
            "placements_existants": [
                {"name": p.name, "group": p.placement_group, "priority": p.priority}
                for p in campaign.placement_ids
            ],
        })
        return payload

    def _format_targeting_analysis(self, data):
        return (
            "<h4>Stratégie de ciblage</h4><p>%s</p>"
            "<h4>Audiences prospection</h4><p>%s</p>"
            "<h4>Remarketing</h4><p>%s</p>"
            "<h4>Placements Meta</h4><p>%s</p>"
            "<h4>Recommandations</h4><p>%s</p>"
        ) % (
            data.get("strategie_ciblage", ""),
            data.get("audiences_resume", ""),
            data.get("remarketing_resume", ""),
            data.get("placements_resume", ""),
            data.get("recommandations", ""),
        )

    def _build_strategy_adjustment_payload(self, campaign):
        payload = self._build_targeting_payload(campaign)
        foundation = campaign.foundation_id
        payload.update({
            "diagnostic_auto": campaign.optimization_summary,
            "recommandation_auto": campaign.ai_recommendation,
            "sante": campaign.optimization_health,
            "analyse_creatifs": campaign.creative_brand_analysis or "",
            "analyse_ciblage": campaign.targeting_strategy_analysis or "",
            "strategie_marque": foundation.brand_strategy,
            "analyse_humaine": campaign.human_analysis or "",
            "notes_reajustement": campaign.strategy_adjustment_notes or "",
        })
        return payload

    def _format_strategy_adjusted(self, data):
        plan = data.get("plan_action") or []
        plan_html = "".join("<li>%s</li>" % p for p in plan)
        priorites = data.get("priorites") or {}
        prio_html = "".join(
            "<li><b>%s</b> — %s</li>" % (k, v)
            for k, v in priorites.items()
        )
        strategie = data.get("strategie_reajustee") or ""
        if strategie and not strategie.strip().startswith("<"):
            strategie = "<p>%s</p>" % strategie
        return (
            "%s"
            "<h4>Plan d'action</h4><ul>%s</ul>"
            "<h4>Priorités</h4><ul>%s</ul>"
            "<p><i>%s</i></p>"
        ) % (
            strategie,
            plan_html or "<li>—</li>",
            prio_html or "<li>—</li>",
            data.get("resume_synthese", ""),
        )

    def synthesize_strategy_adjustment(self, campaign):
        """Consolide analyse humaine + diagnostics en stratégie réajustée."""
        campaign.ensure_one()
        payload = self._build_strategy_adjustment_payload(campaign)
        data = self.env["doorway.traffic.claude.service"].adjust_strategy_from_human(
            payload
        )
        plan_text = "\n".join(
            "- %s" % p for p in (data.get("plan_action") or [])
        )
        vals = {
            "strategy_adjusted": self._format_strategy_adjusted(data),
            "strategy_action_plan": plan_text,
            "strategy_adjusted_at": fields.Datetime.now(),
            "strategy_adjusted_by": self.env.user.id,
            "optimization_customized": True,
        }
        brief = (data.get("brief_creatifs") or "").strip()
        if brief and "<" not in brief[:30]:
            vals["optimization_brief"] = brief
        elif campaign.strategy_adjustment_notes:
            vals["optimization_brief"] = campaign.strategy_adjustment_notes
        action = data.get("action_recommandee")
        if action and action != "none":
            vals["ai_action_pending"] = action
        priorites = data.get("priorites") or {}
        budget_prio = priorites.get("budget") or ""
        if "réduire" in budget_prio.lower() or "baisser" in budget_prio.lower():
            daily = campaign.budget_daily or campaign.optimization_budget_daily
            if daily:
                vals["optimization_budget_daily"] = round(daily * 0.85, 2)
        reco = data.get("resume_synthese")
        if reco:
            vals["ai_recommendation"] = reco
        campaign.write(vals)
        campaign.message_post(
            body=_("Stratégie réajustée à partir de l'analyse humaine.")
        )
        return data

    def apply_human_strategy_realignment(self, campaign):
        """Relance analyses et suggestions selon la stratégie réajustée."""
        campaign.ensure_one()
        self.analyze_brand_creatives(campaign)
        self.analyze_targeting_strategy(campaign)
        self.suggest_targeting(campaign, force=True)
        self.suggest_creatives(campaign, force=True)
        campaign.message_post(
            body=_(
                "Réajustement appliqué — créatifs, audiences, remarketing et "
                "placements régénérés selon la stratégie humaine."
            )
        )
        return True

    def analyze_targeting_strategy(self, campaign):
        campaign.ensure_one()
        payload = self._build_targeting_payload(campaign)
        data = self.env["doorway.traffic.claude.service"].analyze_targeting_strategy(
            payload
        )
        campaign.write({
            "targeting_strategy_analysis": self._format_targeting_analysis(data),
        })
        return data

    def suggest_targeting(self, campaign, force=False):
        """Génère audiences, remarketing et placements proposés."""
        campaign.ensure_one()
        Audience = self.env["doorway.audience"]
        Placement = self.env["doorway.placement"]

        if force:
            Audience.search([
                ("campaign_id", "=", campaign.id),
                ("ai_status", "=", "proposed"),
            ]).write({"ai_status": "rejected"})
            Placement.search([
                ("campaign_id", "=", campaign.id),
                ("ai_status", "=", "proposed"),
            ]).write({"ai_status": "rejected"})
        else:
            has_aud = Audience.search_count([
                ("campaign_id", "=", campaign.id),
                ("ai_status", "=", "proposed"),
            ])
            has_plc = Placement.search_count([
                ("campaign_id", "=", campaign.id),
                ("ai_status", "=", "proposed"),
            ])
            if has_aud >= 2 and has_plc >= 2:
                return Audience.browse(), Placement.browse()

        if not campaign.targeting_strategy_analysis:
            self.analyze_targeting_strategy(campaign)

        payload = self._build_targeting_payload(campaign)
        data = self.env["doorway.traffic.claude.service"].suggest_targeting(payload)

        created_aud = Audience.browse()
        for aud in (data.get("audiences") or [])[:3]:
            targeting = aud.get("targeting")
            if isinstance(targeting, dict):
                targeting = json.dumps(targeting, ensure_ascii=False)
            created_aud |= Audience.create({
                "campaign_id": campaign.id,
                "name": aud.get("name") or "Audience IA",
                "description": aud.get("description"),
                "audience_type": aud.get("audience_type") or "cold",
                "platform": aud.get("platform") or "meta",
                "targeting": targeting or "{}",
                "estimated_size": aud.get("estimated_size") or 0,
                "targeting_rationale": aud.get("rationale"),
                "source": "ai_generated",
                "ai_status": "proposed",
            })

        for rem in (data.get("remarketing") or [])[:3]:
            created_aud |= Audience.create({
                "campaign_id": campaign.id,
                "name": rem.get("name") or "Remarketing IA",
                "description": rem.get("description"),
                "audience_type": "retargeting",
                "remarketing_source": rem.get("remarketing_source") or "website_visitors",
                "window_days": rem.get("window_days") or 30,
                "platform": "meta",
                "targeting": json.dumps({
                    "source": rem.get("remarketing_source"),
                    "window_days": rem.get("window_days") or 30,
                }, ensure_ascii=False),
                "targeting_rationale": rem.get("rationale"),
                "source": "ai_generated",
                "ai_status": "proposed",
            })

        created_plc = Placement.browse()
        for plc in (data.get("placements") or [])[:5]:
            group = plc.get("placement_group") or "facebook_feed"
            created_plc |= Placement.create({
                "campaign_id": campaign.id,
                "name": plc.get("name") or group,
                "placement_group": group,
                "platform": "meta",
                "priority": plc.get("priority") or "medium",
                "placement_rationale": plc.get("rationale"),
                "source": "ai_generated",
                "ai_status": "proposed",
            })

        total = len(created_aud) + len(created_plc)
        if total:
            campaign.message_post(
                body=_(
                    "Ciblage IA : %s audience(s)/remarketing + %s placement(s) proposés."
                )
                % (len(created_aud), len(created_plc))
            )
        return created_aud, created_plc

    def _match_meta_campaign(self, foundation, odoo_campaign, meta_campaigns):
        brand = foundation.brand_name or ""
        explicit = PORTFOLIO_META_CAMPAIGN_IDS.get(brand)
        if explicit and explicit[0]:
            ext_id = explicit[0]
            for mc in meta_campaigns:
                if str(mc.get("id")) == str(ext_id):
                    return mc
            return {"id": ext_id, "name": explicit[1] or ext_id}
        keywords = PORTFOLIO_META_KEYWORDS.get(brand, [])
        brand_tokens = [
            t
            for t in brand.lower().replace("é", "e").replace("è", "e").split()
            if len(t) > 3
        ]
        keywords = keywords + brand_tokens

        def score(mc):
            name = (mc.get("name") or "").lower()
            name_norm = name.replace("é", "e").replace("è", "e")
            pts = 0
            for kw in keywords:
                if kw in name_norm:
                    pts += 10
            if (mc.get("status") or "").upper() == "ACTIVE":
                pts += 5
            odoo_name = (odoo_campaign.name or "").lower()
            if name_norm and name_norm in odoo_name:
                pts += 3
            return pts

        ranked = sorted(meta_campaigns, key=score, reverse=True)
        best = ranked[0] if ranked and score(ranked[0]) > 0 else None
        return best

    def sync_campaign_performance(self, campaign, date_preset="last_7d"):
        campaign.ensure_one()
        foundation = campaign.foundation_id
        channel = campaign.channel_id.code if campaign.channel_id else "meta"

        if channel == "meta":
            return self._sync_meta_campaign(campaign, foundation, date_preset)
        if channel == "google":
            return self._sync_google_campaign(campaign, foundation)
        if channel == "tiktok":
            return self._sync_tiktok_campaign(campaign, foundation)
        raise UserError(_("Canal %s non supporté pour la sync.") % channel)

    def _sync_meta_campaign(self, campaign, foundation, date_preset="last_7d"):
        connector = self._meta_connector(foundation)

        list_res = connector.list_campaigns(limit=100)
        if not list_res["ok"]:
            raise UserError(_("Meta Ads : %s") % list_res["message"])
        meta_campaigns = (list_res.get("data") or {}).get("data") or []
        matched = self._campaigns_matching_portfolio(foundation, meta_campaigns)

        if not matched:
            raise UserError(
                _(
                    "Aucune campagne Meta trouvée pour « %s ». "
                    "Vérifiez les mots-clés ou renseignez external_campaign_id."
                )
                % foundation.brand_name
            )

        metrics_7d = []
        metrics_30d = []
        matched_info = []
        primary = matched[0]
        for mc in matched:
            cid = mc.get("id")
            name = mc.get("name")
            status = mc.get("status")
            for preset, bucket in (("last_7d", metrics_7d), ("last_30d", metrics_30d)):
                ins = connector.fetch_campaign_insights(cid, date_preset=preset)
                if ins["ok"]:
                    bucket.append(connector.parse_insights(ins["data"]))
            matched_info.append({
                "id": cid,
                "name": name,
                "status": status,
            })

        total_7d = connector.merge_metrics(metrics_7d)
        total_30d = connector.merge_metrics(metrics_30d)

        campaign.write({
            "impressions": total_7d["impressions"],
            "clicks": total_7d["clicks"],
            "ctr": total_7d["ctr"],
            "spend": total_7d["spend"],
            "conversions": total_7d["conversions"],
            "cpa": total_7d["cpa"],
            "roas": total_7d["roas"],
            "spend_30d": total_30d["spend"],
            "impressions_30d": total_30d["impressions"],
            "clicks_30d": total_30d["clicks"],
            "ctr_30d": total_30d["ctr"],
            "conversions_30d": total_30d["conversions"],
            "cpa_30d": total_30d["cpa"],
            "external_campaign_id": str(primary.get("id")),
            "meta_campaign_name": primary.get("name"),
            "meta_campaigns_matched": json.dumps(matched_info, ensure_ascii=False),
            "last_sync_at": fields.Datetime.now(),
            "sync_message": _(
                "Sync OK — %s campagne(s) Meta · 7j: %.2f€ · 30j: %.2f€"
            )
            % (len(matched), total_7d["spend"], total_30d["spend"]),
        })
        return total_7d

    def _sync_google_campaign(self, campaign, foundation):
        connector = GoogleAdsConnector(
            foundation.google_account_id,
            self._icp().get_param("doorway_traffic_manager.google_ads_refresh_token"),
        )
        res = connector.fetch_campaign_metrics(campaign.external_campaign_id)
        campaign.sync_message = res.get("message", "")
        if not res["ok"]:
            raise UserError(res["message"])
        return res.get("data") or {}

    def _sync_tiktok_campaign(self, campaign, foundation):
        connector = TikTokAdsConnector(
            self._icp().get_param("doorway_traffic_manager.tiktok_ads_access_token"),
            foundation.tiktok_account_id,
        )
        res = connector.fetch_reports(campaign.external_campaign_id)
        campaign.sync_message = res.get("message", "")
        if not res["ok"]:
            raise UserError(res["message"])
        return res.get("data") or {}

    def publish_campaign(self, campaign):
        """Publie sur la plateforme — uniquement campagne approuvée ou active."""
        campaign.ensure_one()
        if campaign.ai_status not in ("approved", "active"):
            raise UserError(
                _("La campagne doit être approuvée avant publication sur la plateforme.")
            )
        foundation = campaign.foundation_id
        channel = campaign.channel_id.code if campaign.channel_id else "meta"

        if channel == "meta":
            connector = self._meta_connector(foundation)
            daily_cents = int((campaign.budget_daily or 50) * 100)
            objective = OBJECTIVE_META_MAP.get(campaign.objective or "leads", "OUTCOME_LEADS")
            res = connector.create_campaign(campaign.name, objective, daily_cents)
            if not res["ok"]:
                raise UserError(_("Meta Ads : %s") % res["message"])
            ext_id = (res.get("data") or {}).get("id")
            campaign.write({
                "external_campaign_id": ext_id,
                "ai_status": "active",
                "sync_message": _("Campagne créée sur Meta (statut PAUSED)."),
            })
            campaign.message_post(
                body=_("Campagne Meta créée — ID %s (en pause, activation manuelle).") % ext_id
            )
            return res["data"]

        raise UserError(
            _("Publication %s — connecteur en cours de déploiement (Phase 2b).") % channel
        )

    def sync_ga4_summary(self, foundation):
        connector = GA4Connector(
            foundation.ga4_property_id,
            self._icp().get_param("doorway_traffic_manager.ga4_credentials_path"),
        )
        return connector.run_report()

    @api.model
    def cron_sync_all_active_campaigns(self):
        self.sync_all_last_7d(generate_reports=False)

    @api.model
    def sync_optimize_all(self):
        """Corrige liens Meta, sync agrégée 7j+30j, optimisation + créatifs."""
        return self.fix_meta_campaign_links()

    def sync_all_last_7d(self, generate_reports=True):
        """Sync Meta 7 derniers jours + rapports hebdo par portefeuille."""
        from datetime import timedelta

        campaigns = self.env["doorway.traffic.campaign"].search([
            ("ai_status", "in", ["active", "approved", "paused"]),
        ])
        results = {"ok": [], "errors": []}
        for campaign in campaigns:
            try:
                metrics = self.sync_campaign_performance(campaign)
                self._post_sync_optimize(campaign)
                results["ok"].append((campaign.name, metrics))
            except UserError as exc:
                campaign.sync_message = str(exc)
                results["errors"].append((campaign.name, str(exc)))
                _logger.info("Sync campagne %s: %s", campaign.id, exc)
            except Exception as exc:  # noqa: BLE001
                results["errors"].append((campaign.name, str(exc)))
                _logger.warning("Sync campagne %s: %s", campaign.id, exc)

        if generate_reports:
            Report = self.env["doorway.traffic.report"]
            today = fields.Date.today()
            date_from = today - timedelta(days=7)
            for foundation in self.env["doorway.brand.foundation"].search([
                ("state", "=", "validated"),
            ]):
                f_campaigns = campaigns.filtered(
                    lambda c, f=foundation: c.foundation_id == f
                )
                if not f_campaigns:
                    continue
                try:
                    Report._generate_for_foundation(
                        foundation, f_campaigns, date_from, today
                    )
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("Rapport %s: %s", foundation.brand_name, exc)
        return results
