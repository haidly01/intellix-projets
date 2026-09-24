# -*- coding: utf-8 -*-
"""Base de connaissance des portefeuilles Doorway (Meta pages + pipelines)."""
from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.doorway_traffic_manager.services.ad_connectors.meta_connector import (
    MetaAdsConnector,
)

# Portefeuilles documentés : META_LEADS_GLOBAL_MAP + docs HAIDLY / ENERGIE / IMMO
PORTFOLIO_KNOWLEDGE = [
    {
        "brand_name": "Agence Doorway",
        "pipeline_xmlid": "renovation_conciergerie.crm_team_marketing",
        "meta_page_id": "499982889862307",
        "website_url": "https://agencedoorway.com",
        "geographic_zone": "canada",
        "primary_objective": "leads",
        "monthly_budget_eur": 2400.0,
        "target_cpa_eur": 45.0,
        "target_roas": 3.0,
        "target_b2b": True,
        "target_age_min": 28,
        "target_age_max": 55,
        "price_positioning": "premium",
        "communication_style": "vouvoiement",
        "channel_codes": ["meta", "google", "linkedin"],
        "tone_names": ["Expert", "Proximité / Humain"],
        "brand_description": (
            "Agence marketing digital B2B — CRM, IA, SEO, réseaux sociaux "
            "et génération de leads pour PME québécoises."
        ),
        "target_persona": (
            "Dirigeant PME 30-50 ans, cherche à structurer son marketing "
            "ou remplacer une agence peu performante."
        ),
        "target_pain_points": (
            "Leads peu qualifiés\n"
            "Pas de suivi CRM\n"
            "ROI publicitaire flou\n"
            "Manque de temps interne"
        ),
        "main_value_prop": (
            "Intellix CRM + agents IA + campagnes intégrées : "
            "un seul partenaire pour vendre plus avec moins de friction."
        ),
        "competitors": "Agences locales généralistes\nFreelances marketing\nOutils SaaS isolés",
        "competitive_advantage": (
            "Stack Odoo + IA + VICIdial + Traffic Manager sur un seul VPS, "
            "avec équipe Doorway au Québec."
        ),
        "differentiator": (
            "Doorway combine CRM, agents vocaux IA et traffic management "
            "dans une plateforme unifiée — pas seulement des campagnes isolées."
        ),
        "brand_strategy": (
            "Meta Lead Ads + retargeting site + LinkedIn ABM. "
            "Budget 60 % Meta / 30 % Google Search marque+intention / 10 % tests créatifs."
        ),
        "tracking_method": (
            "GA4 : generate_lead, form_submit. Meta CAPI + Google Ads conversions. "
            "Dashboard Traffic Manager hebdo."
        ),
        "brand_voice_guide": (
            "Vouvoiement, ton expert-accessible. Éviter le jargon startup. "
            "Mettre en avant résultats concrets et stack Intellix."
        ),
        "suggested_kpis": "CPA < 45 € · 80 leads/mois · ROAS 3x · CTR Meta > 1.2 %",
    },
    {
        "brand_name": "Maison Recherchée",
        "pipeline_xmlid": "renovation_conciergerie.crm_team_immobilier",
        "meta_page_id": "964640820063787",
        "website_url": "https://intellixcrm.com",
        "geographic_zone": "local",
        "primary_objective": "leads",
        "monthly_budget_eur": 1800.0,
        "target_cpa_eur": 35.0,
        "target_roas": 4.0,
        "target_b2c": True,
        "target_age_min": 35,
        "target_age_max": 65,
        "price_positioning": "mid",
        "communication_style": "vouvoiement",
        "channel_codes": ["meta", "google"],
        "tone_names": ["Proximité / Humain", "Expert"],
        "brand_description": (
            "Service immobilier / rénovation orienté propriétaires québécois "
            "cherchant une soumission ou un projet qualifié."
        ),
        "target_persona": (
            "Propriétaire résidentiel 40-60 ans, projet réno ou achat, "
            "recherche conseil et soumission fiable."
        ),
        "target_pain_points": (
            "Difficulté à comparer les soumissions\n"
            "Peur des arnaques\n"
            "Projet flou sans budget"
        ),
        "main_value_prop": (
            "Qualification immédiate par agent IA Sophie + suivi CRM structuré."
        ),
        "competitors": "Courtier local\nSites de soumission génériques\nContracteurs au bouche-à-oreille",
        "competitive_advantage": "Agent IA J+0 + relances J+1 à J+14 intégrées Odoo.",
        "differentiator": "Parcours vocal IA + pipeline immobilier dédié avec relances automatisées.",
        "brand_strategy": "Meta Lead Ads formulaire court + retargeting visiteurs. Google local intent.",
        "tracking_method": "Lead Ads form_id 1016997697520697 · webhook meta-immo-lead · GA4 lead.",
        "brand_voice_guide": "Rassurant, concret, québécois. Mettre l'accent sur l'accompagnement humain.",
        "suggested_kpis": "CPA < 35 € · 60 leads qualifiés/mois · taux contact J+0 > 40 %",
    },
    {
        "brand_name": "Haidly Rénovation",
        "pipeline_xmlid": "renovation_conciergerie.crm_team_renovation",
        "meta_page_id": "574384345749047",
        "website_url": "https://soumissionentrepreneurs.com",
        "geographic_zone": "local",
        "primary_objective": "leads",
        "monthly_budget_eur": 2000.0,
        "target_cpa_eur": 30.0,
        "target_roas": 3.5,
        "target_b2c": True,
        "target_age_min": 30,
        "target_age_max": 60,
        "price_positioning": "mid",
        "communication_style": "vouvoiement",
        "channel_codes": ["meta", "google"],
        "tone_names": ["Proximité / Humain", "Éducatif"],
        "brand_description": (
            "Conciergerie rénovation — SoumissionEntrepreneurs.com. "
            "Qualification vocale IA et suivi subventions."
        ),
        "target_persona": "Propriétaire avec projet réno toiture, cuisine, sous-sol au Québec.",
        "target_pain_points": "Budget flou\nPeur du mauvais entrepreneur\nManque de temps",
        "main_value_prop": "Agent Haidly J+0 + relances photos/subventions J+1 à J+14.",
        "competitors": "SoumissionRenovation.ca\nContracteurs locaux\nMarketplaces B2C",
        "competitive_advantage": "Voix FR-CA expressif + pipeline Rénovation Odoo + page Meta Haidly.",
        "differentiator": "Conciergerie complète réno avec IA vocale et upload photos intégré.",
        "brand_strategy": "Meta Lead Ads + contenu éducatif subventions. Retargeting site SEP.",
        "tracking_method": "Webhook haidly-lead · form 1177919251120913 · GA4 generate_lead.",
        "brand_voice_guide": "Ton chaleureux québécois, tutoiement évité. Angle subventions et confiance.",
        "suggested_kpis": "CPA < 30 € · 70 leads/mois · appels J+0 > 35 %",
    },
    {
        "brand_name": "ICI Thermopompe",
        "pipeline_xmlid": "renovation_conciergerie.crm_team_renovation",
        "meta_page_id": "962295250303049",
        "website_url": "https://icithermopompe.com",
        "geographic_zone": "local",
        "primary_objective": "leads",
        "monthly_budget_eur": 1500.0,
        "target_cpa_eur": 40.0,
        "target_roas": 3.0,
        "target_b2c": True,
        "target_age_min": 35,
        "target_age_max": 65,
        "price_positioning": "mid",
        "channel_codes": ["meta", "google"],
        "tone_names": ["Expert", "Éducatif"],
        "brand_description": "Thermopompes et efficacité énergétique résidentielle — Québec.",
        "target_persona": "Propriétaire maison détachée, facture chauffage élevée, subventions Rénoclimat.",
        "target_pain_points": "Coûts énergie\nComplexité subventions\nChoix du bon modèle",
        "main_value_prop": "Agent Alex Énergie Pro + qualification subventions et installation.",
        "competitors": "Installateurs locaux\nGéants box store\nSites comparateurs",
        "competitive_advantage": "Lead Ads janv. 2026 + agent IA Énergie intégré Odoo.",
        "differentiator": "Spécialiste thermopompe QC avec qualification IA et suivi CRM énergie.",
        "brand_strategy": "Meta Lead Ads thermopompe + Google search intent hiver. Retargeting 30j.",
        "tracking_method": "energie-lead webhook · form 1912811406106600 · tag site icithermopompe.",
        "brand_voice_guide": "Expert rassurant, chiffres concrets économies annuelles, subventions.",
        "suggested_kpis": "CPA < 40 € · 50 leads/mois · ROAS 3x",
    },
    {
        "brand_name": "Énergie Pro",
        "pipeline_xmlid": "renovation_conciergerie.crm_team_renovation",
        "meta_page_id": "1004010452788312",
        "website_url": "https://intellixcrm.com",
        "geographic_zone": "local",
        "primary_objective": "leads",
        "monthly_budget_eur": 1200.0,
        "target_cpa_eur": 42.0,
        "target_roas": 3.0,
        "target_b2c": True,
        "target_age_min": 30,
        "target_age_max": 65,
        "price_positioning": "mid",
        "channel_codes": ["meta", "google"],
        "tone_names": ["Expert", "Promotionnel"],
        "brand_description": (
            "Page générale Énergie Pro — isolation, thermopompe, portes/fenêtres QC."
        ),
        "target_persona": "Propriétaire souhaitant réduire facture énergétique ou rénover enveloppe.",
        "target_pain_points": "Factures élevées\nSubventions incomprises\nMulti-travaux",
        "main_value_prop": "Un seul point d'entrée pour projets énergie avec agent Alex.",
        "competitors": "Isolation QC\nThermopompe locale\nProgrammes gouvernementaux seuls",
        "competitive_advantage": "Hub énergie multi-projets + round-robin agents IA Odoo.",
        "differentiator": "Portefeuille énergie unifié Doorway avec routage intelligent par site.",
        "brand_strategy": "Meta broad énergie QC + remarketing. Tests créatifs isolation vs thermopompe.",
        "tracking_method": "energie-lead · page map JSON · GA4 par site energie_pro.",
        "brand_voice_guide": "Direct, orienté économies et subventions. Éviter le vertwashing.",
        "suggested_kpis": "CPA < 42 € · 40 leads/mois · CTR > 1 %",
    },
]


class DoorwayPortfolioKnowledge(models.AbstractModel):
    _name = "doorway.portfolio.knowledge"
    _description = "Import portefeuilles Traffic Manager"

    @api.model
    def _resolve_tone_ids(self, tone_names):
        Tag = self.env["doorway.brand.tone.tag"]
        return Tag.search([("name", "in", tone_names)]).ids

    @api.model
    def _resolve_channel_ids(self, channel_codes):
        Channel = self.env["doorway.traffic.channel"]
        return Channel.search([("code", "in", channel_codes)]).ids

    @api.model
    def _link_social_account(self, meta_page_id, foundation):
        if not meta_page_id or "doorway.social.account" not in self.env:
            return
        account = self.env["doorway.social.account"].sudo().search([
            ("platform", "=", "facebook"),
            ("external_account_id", "=", meta_page_id),
        ], limit=1)
        if account and not account.pipeline_id:
            account.pipeline_id = foundation.pipeline_id.id

    @api.model
    def import_all_portfolios(self):
        Foundation = self.env["doorway.brand.foundation"].sudo()
        created = Foundation.browse()
        errors = []

        for data in PORTFOLIO_KNOWLEDGE:
            team = self.env.ref(data["pipeline_xmlid"], raise_if_not_found=False)
            if not team:
                errors.append("Pipeline introuvable : %s" % data["pipeline_xmlid"])
                continue

            domain = [("meta_page_id", "=", data["meta_page_id"])]
            existing = Foundation.search(domain, limit=1)
            vals = {
                "pipeline_id": team.id,
                "brand_name": data["brand_name"],
                "meta_page_id": data["meta_page_id"],
                "meta_account_id": data.get("meta_account_id") or False,
                "website_url": data.get("website_url"),
                "geographic_zone": data.get("geographic_zone", "canada"),
                "primary_objective": data.get("primary_objective", "leads"),
                "monthly_budget_eur": data.get("monthly_budget_eur", 0),
                "target_cpa_eur": data.get("target_cpa_eur", 0),
                "target_roas": data.get("target_roas", 0),
                "target_b2c": data.get("target_b2c", True),
                "target_b2b": data.get("target_b2b", False),
                "target_age_min": data.get("target_age_min"),
                "target_age_max": data.get("target_age_max"),
                "price_positioning": data.get("price_positioning", "mid"),
                "communication_style": data.get("communication_style", "vouvoiement"),
                "brand_description": data.get("brand_description"),
                "target_persona": data.get("target_persona"),
                "target_pain_points": data.get("target_pain_points"),
                "main_value_prop": data.get("main_value_prop"),
                "competitors": data.get("competitors"),
                "competitive_advantage": data.get("competitive_advantage"),
                "differentiator": data.get("differentiator"),
                "brand_strategy": data.get("brand_strategy"),
                "tracking_method": data.get("tracking_method"),
                "brand_voice_guide": data.get("brand_voice_guide"),
                "suggested_kpis": data.get("suggested_kpis"),
                "state": "validated",
            }
            if data.get("tone_names"):
                vals["brand_tone_ids"] = [(6, 0, self._resolve_tone_ids(data["tone_names"]))]
            if data.get("channel_codes"):
                vals["active_channel_ids"] = [
                    (6, 0, self._resolve_channel_ids(data["channel_codes"]))
                ]

            page_id = data["meta_page_id"]
            if existing:
                if MetaAdsConnector.is_placeholder_account(
                    existing.meta_account_id, page_id
                ):
                    vals["meta_account_id"] = data.get("meta_account_id") or False
                existing.write(vals)
                rec = existing
            else:
                rec = Foundation.create(vals)
            self._link_social_account(data["meta_page_id"], rec)
            created |= rec

        if errors and not created:
            raise UserError("\n".join(errors))
        return created

    @api.model
    def bootstrap_campaigns_from_portfolios(self):
        """Crée une campagne Meta active par portefeuille validé (si absente)."""
        Campaign = self.env["doorway.traffic.campaign"].sudo()
        Channel = self.env["doorway.traffic.channel"]
        meta = Channel.search([("code", "=", "meta")], limit=1)
        if not meta:
            raise UserError(_("Canal Meta introuvable."))

        created = Campaign.browse()
        for foundation in self.env["doorway.brand.foundation"].search([
            ("state", "=", "validated"),
        ]):
            if Campaign.search([("foundation_id", "=", foundation.id)], limit=1):
                continue
            monthly = foundation.monthly_budget_eur or 0
            daily = round(monthly / 30.0, 2) if monthly else 50.0
            created |= Campaign.create({
                "name": "%s — Meta Leads" % foundation.brand_name,
                "foundation_id": foundation.id,
                "channel_id": meta.id,
                "objective": foundation.primary_objective or "leads",
                "budget_total": monthly,
                "budget_daily": daily,
                "ai_status": "active",
                "ai_recommendation": (foundation.brand_strategy or "")[:500],
            })
        return created
