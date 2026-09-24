# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)

BRAND_ANALYSIS_SYSTEM = """Tu es un expert en stratégie marketing et publicité digitale.
Analyse les données de cette marque et génère une réponse JSON uniquement, sans texte autour.
Format :
{
  "differentiator": "La proposition de valeur unique en 2-3 phrases percutantes",
  "strategy": "La stratégie recommandée : canaux prioritaires, séquence, budget allocation, approche créative",
  "tracking": "Méthode de suivi : quels événements GA4 configurer, quelles conversions Meta/Google, quel dashboard",
  "voice_guide": "Guide de ton et de voix : formulations à utiliser, à éviter, exemples de phrases",
  "kpis": "KPIs prioritaires avec objectifs chiffrés basés sur le budget et le secteur"
}"""

CAMPAIGN_GENERATION_SYSTEM = """Tu es un expert media buyer digital.
Génère une structure de campagne publicitaire en JSON uniquement.
Format :
{
  "strategy_notes": "Notes stratégiques en 2-3 phrases",
  "audiences": [
    {
      "name": "Nom audience",
      "description": "Description",
      "audience_type": "cold|warm|hot|lookalike|retargeting|custom",
      "platform": "meta|google|tiktok|linkedin",
      "targeting": {"age_min": 25, "age_max": 55, "interests": ["..."]},
      "estimated_size": 50000
    }
  ],
  "creatives": [
    {
      "format": "image|video|carousel|story|reel|text_ad",
      "headline": "Titre accrocheur",
      "body": "Corps du message",
      "cta": "En savoir plus"
    }
  ]
}"""

OPTIMIZATION_SYSTEM = """Tu es un expert en optimisation de campagnes publicitaires digitales.
Analyse les données de performance et retourne UNIQUEMENT un JSON valide.
Format :
{
  "diagnostic": "Résumé de la situation en 2 phrases",
  "action_priority": "scale_up|scale_down|pause|new_audience|new_creative|none",
  "action_reason": "Raison en 1 phrase",
  "action_detail": "Détail précis de l'action recommandée",
  "audiences_to_pause": ["nom audience si fréquence > 3.5"],
  "creatives_to_boost": ["format du créatif gagnant"]
}"""

WEEKLY_REPORT_SYSTEM = """Tu es analyste performance marketing.
Génère un rapport hebdomadaire en JSON uniquement.
Format :
{
  "summary": "Synthèse exécutive en 3-4 phrases",
  "wins": "Ce qui a bien fonctionné",
  "concerns": "Points d'attention",
  "next_actions": "3 actions prioritaires pour la semaine prochaine",
  "kpi_status": "État des KPIs vs objectifs"
}"""


class DoorwayTrafficClaudeService(models.AbstractModel):
    _name = "doorway.traffic.claude.service"
    _description = "Service Claude — Traffic Manager IA"

    def _api_key(self):
        icp = self.env["ir.config_parameter"].sudo()
        return (
            icp.get_param("doorway_traffic_manager.anthropic_api_key")
            or icp.get_param("doorway_agents_dashboard.anthropic_api_key")
            or icp.get_param("doorway_social_ia.anthropic_api_key")
            or ""
        )

    def _call(self, system, user, model="claude-sonnet-4-20250514", max_tokens=3000):
        import requests

        key = self._api_key()
        if not key:
            _logger.warning("Anthropic API key manquante (Traffic Manager)")
            return ""
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=90,
            )
            if resp.status_code != 200:
                _logger.warning("Claude HTTP %s: %s", resp.status_code, resp.text[:200])
                return ""
            parts = resp.json().get("content") or []
            return "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Claude API Traffic: %s", exc)
            return ""

    def _parse_json(self, text):
        if not text:
            return {}
        match = re.search(r"\{[\s\S]*\}", text)
        try:
            return json.loads(match.group(0) if match else text)
        except json.JSONDecodeError:
            return {}

    def analyze_brand(self, foundation):
        payload = {
            "nom": foundation.brand_name,
            "description": foundation.brand_description,
            "zone": foundation.geographic_zone,
            "cible": foundation.target_persona,
            "pain_points": foundation.target_pain_points,
            "positionnement": foundation.price_positioning,
            "valeur_prop": foundation.main_value_prop,
            "concurrents": foundation.competitors,
            "avantage": foundation.competitive_advantage,
            "ton": foundation.brand_tone_ids.mapped("name"),
            "objectif": foundation.primary_objective,
            "budget": foundation.monthly_budget_eur,
            "cpa_cible": foundation.target_cpa_eur,
            "canaux_actifs": foundation.active_channel_ids.mapped("name"),
        }
        raw = self._call(
            BRAND_ANALYSIS_SYSTEM,
            f"Données marque : {json.dumps(payload, ensure_ascii=False)}",
        )
        data = self._parse_json(raw)
        if not data:
            data = self._fallback_brand_analysis(foundation)
        return data

    def _fallback_brand_analysis(self, foundation):
        return {
            "differentiator": foundation.main_value_prop or foundation.brand_description or "",
            "strategy": (
                f"Prioriser {foundation.primary_objective or 'leads'} sur "
                f"{', '.join(foundation.active_channel_ids.mapped('name')) or 'Meta et Google'} "
                f"avec un budget mensuel de {foundation.monthly_budget_eur or 0} €."
            ),
            "tracking": (
                "Configurer les conversions leads dans GA4 et les événements "
                "Meta/Google Ads. Suivre CPA et ROAS hebdomadairement."
            ),
            "voice_guide": (
                f"Ton : {', '.join(foundation.brand_tone_ids.mapped('name')) or 'professionnel'}. "
                f"Style : {foundation.communication_style or 'vouvoiement'}."
            ),
            "kpis": (
                f"CPA cible : {foundation.target_cpa_eur or '—'} € · "
                f"ROAS cible : {foundation.target_roas or '—'}x · "
                f"Budget : {foundation.monthly_budget_eur or 0} €/mois"
            ),
        }

    def generate_campaign(self, campaign, foundation):
        payload = {
            "marque": foundation.brand_name,
            "strategie": foundation.brand_strategy,
            "differentiateur": foundation.differentiator,
            "objectif_campagne": campaign.objective,
            "canal": campaign.channel_id.name if campaign.channel_id else "",
            "budget_total": campaign.budget_total,
            "budget_journalier": campaign.budget_daily,
        }
        raw = self._call(
            CAMPAIGN_GENERATION_SYSTEM,
            f"Créer campagne : {json.dumps(payload, ensure_ascii=False)}",
        )
        data = self._parse_json(raw)
        if not data.get("audiences"):
            data = self._fallback_campaign(campaign, foundation)
        return data

    def _fallback_campaign(self, campaign, foundation):
        channel = campaign.channel_id.code if campaign.channel_id else "meta"
        return {
            "strategy_notes": (
                f"Campagne {campaign.objective or 'leads'} pour {foundation.brand_name} "
                f"sur {campaign.channel_id.name or 'Meta'}."
            ),
            "audiences": [
                {
                    "name": "Prospection — Intérêts secteur",
                    "description": "Audience froide basée sur les intérêts de la cible",
                    "audience_type": "cold",
                    "platform": channel,
                    "targeting": {"age_min": foundation.target_age_min or 25,
                                  "age_max": foundation.target_age_max or 55},
                    "estimated_size": 100000,
                },
                {
                    "name": "Retargeting — Visiteurs site",
                    "description": "Visiteurs 30 derniers jours",
                    "audience_type": "retargeting",
                    "platform": channel,
                    "targeting": {"window_days": 30},
                    "estimated_size": 5000,
                },
            ],
            "creatives": [
                {
                    "format": "image",
                    "headline": foundation.main_value_prop[:60] if foundation.main_value_prop else "Découvrez notre offre",
                    "body": foundation.differentiator or foundation.brand_description or "",
                    "cta": "En savoir plus",
                },
            ],
        }

    def optimize_campaign(self, perf_data):
        raw = self._call(
            OPTIMIZATION_SYSTEM,
            f"Performance : {json.dumps(perf_data, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
        )
        data = self._parse_json(raw)
        if not data:
            data = {
                "diagnostic": "Données insuffisantes pour une recommandation IA.",
                "action_priority": "none",
                "action_reason": "Continuer la collecte de données.",
                "action_detail": "",
                "audiences_to_pause": [],
                "creatives_to_boost": [],
            }
        return data

    BRAND_CREATIVE_ANALYSIS_SYSTEM = """Tu es stratège créatif performance Meta Ads Québec.
Analyse la marque, l'offre et les performances publicitaires pour recommander des angles créatifs.
Réponds en JSON uniquement :
{
  "marque_resume": "2-3 phrases sur l'identité et le positionnement",
  "offre_resume": "2-3 phrases sur la proposition de valeur et ce qui est vendu",
  "diagnostic_perf": "Analyse CTR/CPA/dépenses et ce que ça signifie pour les créatifs",
  "contenus_a_favoriser": ["élément 1", "élément 2"],
  "contenus_a_eviter": ["élément 1", "élément 2"],
  "angles_creatifs": [
    {
      "angle": "Nom de l'angle",
      "format": "image|video|carousel",
      "justification": "Pourquoi cet angle pour cette marque/offre"
    }
  ],
  "recommandations": "3-5 phrases actionnables pour les prochains créatifs"
}"""

    CREATIVE_SUGGESTION_SYSTEM = """Tu es directeur créatif performance Meta Ads Québec.
Génère 3 variantes de créatifs publicitaires ancrées sur la MARQUE, l'OFFRE et l'analyse fournie.
Chaque créatif doit exploiter un angle différent et respecter le guide de voix.
Si brief_utilisateur est fourni, il est prioritaire.
Réponds en JSON uniquement :
{
  "creatives": [
    {
      "format": "image|video|carousel",
      "headline": "...",
      "body": "...",
      "cta": "...",
      "angle": "Nom de l'angle marketing",
      "rationale": "Lien explicite marque + offre + performance",
      "canva_brief": "Brief visuel Canva ancré marque",
      "visual_description": "Description visuelle pour le designer"
    }
  ]
}"""

    CANVA_BRIEF_SYSTEM = """Tu es directeur artistique pour publicités Meta Ads Québec.
Génère un brief visuel Canva ancré sur la marque et l'offre. JSON uniquement :
{"canva_brief": "...", "visual_description": "..."}"""

    def suggest_canva_brief(self, payload):
        raw = self._call(
            self.CANVA_BRIEF_SYSTEM,
            f"Contexte : {json.dumps(payload, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
        )
        data = self._parse_json(raw)
        return data.get("canva_brief") or data.get("visual_description") or ""

    def analyze_brand_creatives(self, payload):
        raw = self._call(
            self.BRAND_CREATIVE_ANALYSIS_SYSTEM,
            f"Contexte : {json.dumps(payload, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
        )
        data = self._parse_json(raw)
        if data.get("marque_resume") or data.get("angles_creatifs"):
            return data
        return self._fallback_brand_creative_analysis(payload)

    def _fallback_brand_creative_analysis(self, payload):
        marque = payload.get("marque") or "Marque"
        offre = payload.get("offre") or payload.get("valeur") or ""
        return {
            "marque_resume": (
                f"{marque} — {payload.get('description') or ''}"
            ).strip(),
            "offre_resume": offre or "Proposition de valeur à renforcer dans les créatifs.",
            "diagnostic_perf": payload.get("probleme") or "Analyser CTR et CPA pour ajuster les accroches.",
            "contenus_a_favoriser": [
                x for x in (payload.get("contenus_performants") or "").split("\n") if x.strip()
            ][:3] or ["Preuve sociale locale", "Bénéfice concret chiffré"],
            "contenus_a_eviter": [
                x for x in (payload.get("contenus_faibles") or "").split("\n") if x.strip()
            ][:3] or ["Messages génériques sans lien offre"],
            "angles_creatifs": [
                {
                    "angle": "Urgence + offre",
                    "format": "image",
                    "justification": f"Mettre en avant : {offre[:80]}",
                },
                {
                    "angle": "Preuve sociale",
                    "format": "video",
                    "justification": "Témoignage client aligné sur le persona cible.",
                },
                {
                    "angle": "Éducation / valeur",
                    "format": "carousel",
                    "justification": "Expliquer l'offre en 3 slides pour améliorer le CTR.",
                },
            ],
            "recommandations": (
                f"Tester 3 angles pour {marque} en restant fidèle à : {offre[:120]}"
            ),
        }

    STRATEGY_ADJUSTMENT_SYSTEM = """Tu es directeur stratégie media buying.
Consolide l'analyse HUMAINE de l'expert avec les diagnostics automatiques (perf, créatifs, ciblage).
Produis un réajustement de stratégie actionnable pour les 2 prochaines semaines.
Réponds en JSON uniquement :
{
  "strategie_reajustee": "Paragraphe stratégie consolidée (marque + offre + priorités)",
  "plan_action": ["action 1", "action 2", "action 3"],
  "priorites": {
    "creatifs": "priorité créatifs",
    "ciblage": "priorité audiences/remarketing/placements",
    "budget": "priorité budget et pacing"
  },
  "action_recommandee": "scale_up|scale_down|pause|new_audience|new_creative|fix_link|none",
  "brief_creatifs": "Instructions créatifs dérivées de l'analyse humaine",
  "resume_synthese": "3-4 phrases : constat humain + décision stratégique"
}"""

    TARGETING_ANALYSIS_SYSTEM = """Tu es media buyer Meta Ads Québec.
Analyse le ciblage optimal : audiences prospection, remarketing et placements Meta.
Réponds en JSON uniquement :
{
  "strategie_ciblage": "3-5 phrases sur la stratégie globale",
  "audiences_resume": "Résumé audiences prospection recommandées",
  "remarketing_resume": "Résumé remarketing recommandé",
  "placements_resume": "Résumé placements Meta recommandés",
  "recommandations": "Actions prioritaires ciblage"
}"""

    TARGETING_SUGGESTION_SYSTEM = """Tu es media buyer Meta Ads Québec.
Propose audiences prospection, segments remarketing et placements Meta adaptés à la marque.
Réponds en JSON uniquement :
{
  "audiences": [
    {
      "name": "...",
      "audience_type": "cold|warm|lookalike|hot",
      "description": "...",
      "platform": "meta",
      "estimated_size": 100000,
      "targeting": {"age_min": 35, "age_max": 65, "interests": ["..."]},
      "rationale": "..."
    }
  ],
  "remarketing": [
    {
      "name": "...",
      "remarketing_source": "website_visitors|lead_form_openers|video_viewers|page_engagers|ig_engagers",
      "window_days": 30,
      "description": "...",
      "rationale": "..."
    }
  ],
  "placements": [
    {
      "name": "Instagram Reels",
      "placement_group": "instagram_reels|facebook_feed|instagram_feed|instagram_stories|facebook_stories|audience_network|messenger|marketplace|explore",
      "priority": "high|medium|low|exclude",
      "rationale": "..."
    }
  ]
}"""

    def adjust_strategy_from_human(self, payload):
        raw = self._call(
            self.STRATEGY_ADJUSTMENT_SYSTEM,
            f"Contexte : {json.dumps(payload, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
        )
        data = self._parse_json(raw)
        if data.get("strategie_reajustee"):
            return data
        return self._fallback_strategy_adjustment(payload)

    def _fallback_strategy_adjustment(self, payload):
        human = payload.get("analyse_humaine") or payload.get("notes_reajustement") or ""
        strategie = payload.get("strategie_marque") or ""
        return {
            "strategie_reajustee": (
                f"<p><b>Stratégie réajustée (expert)</b></p>"
                f"<p>{human or 'Aucune analyse humaine.'}</p>"
                f"<p><i>Base marque :</i> {strategie[:300]}</p>"
            ),
            "plan_action": [
                "Valider les constats humains sur les 7 derniers jours",
                "Tester les créatifs et audiences proposés par l'IA",
                "Réévaluer CPA et budget sous 7 jours",
            ],
            "priorites": {
                "creatifs": payload.get("probleme") or "Optimiser accroches",
                "ciblage": "Remarketing 30j + prospection lookalike",
                "budget": "Maintenir ou réduire selon CPA 7j",
            },
            "action_recommandee": (
                payload.get("action")
                if payload.get("action") not in (None, "none", "")
                else "new_creative"
            ),
            "brief_creatifs": (
                payload.get("notes_reajustement")
                or payload.get("brief_utilisateur")
                or ""
            )[:500],
            "resume_synthese": human[:300] or payload.get("diagnostic_perf") or "",
        }

    def analyze_targeting_strategy(self, payload):
        raw = self._call(
            self.TARGETING_ANALYSIS_SYSTEM,
            f"Contexte : {json.dumps(payload, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
        )
        data = self._parse_json(raw)
        if data.get("strategie_ciblage"):
            return data
        return self._fallback_targeting_analysis(payload)

    def suggest_targeting(self, payload):
        raw = self._call(
            self.TARGETING_SUGGESTION_SYSTEM,
            f"Contexte : {json.dumps(payload, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=1800,
        )
        data = self._parse_json(raw)
        if data.get("audiences") or data.get("remarketing") or data.get("placements"):
            return data
        return self._fallback_targeting_suggestions(payload)

    def _fallback_targeting_analysis(self, payload):
        marque = payload.get("marque") or "Marque"
        return {
            "strategie_ciblage": (
                f"Prospection froide + remarketing 30j pour {marque}. "
                f"Prioriser Feed et Reels si CTR faible."
            ),
            "audiences_resume": (
                "Audience cold : intérêts alignés sur le persona + zone géographique Québec."
            ),
            "remarketing_resume": (
                "Visiteurs site 30j + engagés page 14j + lead form ouvreurs 7j."
            ),
            "placements_resume": (
                "Priorité Instagram Reels et Facebook Feed. Exclure Audience Network si CPA élevé."
            ),
            "recommandations": payload.get("probleme") or "Tester lookalike 1-3 % sur convertisseurs.",
        }

    def _fallback_targeting_suggestions(self, payload):
        import json as json_mod
        marque = payload.get("marque") or "Marque"
        age_min = payload.get("age_min") or 35
        age_max = payload.get("age_max") or 65
        targeting = json_mod.dumps({
            "age_min": age_min,
            "age_max": age_max,
            "geo": "Québec",
            "interests": ["rénovation", "immobilier", "énergie"],
        }, ensure_ascii=False)
        return {
            "audiences": [
                {
                    "name": f"Prospection — {marque}",
                    "audience_type": "cold",
                    "description": "Intérêts + démographie alignés persona",
                    "platform": "meta",
                    "estimated_size": 150000,
                    "targeting": targeting,
                    "rationale": "Acquisition froide principale.",
                },
                {
                    "name": f"Lookalike 1-3 % — convertisseurs",
                    "audience_type": "lookalike",
                    "description": "Lookalike sur leads 90 derniers jours",
                    "platform": "meta",
                    "estimated_size": 80000,
                    "targeting": '{"source": "leads_90d", "ratio": "1-3"}',
                    "rationale": "Scale quand CPA sous cible.",
                },
            ],
            "remarketing": [
                {
                    "name": "Remarketing — visiteurs site 30j",
                    "remarketing_source": "website_visitors",
                    "window_days": 30,
                    "description": "Tous les visiteurs site 30 derniers jours",
                    "rationale": "Récupérer l'intention chaude.",
                },
                {
                    "name": "Remarketing — engagés page 14j",
                    "remarketing_source": "page_engagers",
                    "window_days": 14,
                    "description": "Engagement page Facebook",
                    "rationale": "Audience warm à fort taux de conversion.",
                },
            ],
            "placements": [
                {
                    "name": "Instagram Reels",
                    "placement_group": "instagram_reels",
                    "priority": "high",
                    "rationale": "Meilleur CTR vidéo court format.",
                },
                {
                    "name": "Facebook Feed",
                    "placement_group": "facebook_feed",
                    "priority": "high",
                    "rationale": "Volume et leads formulaire.",
                },
                {
                    "name": "Audience Network",
                    "placement_group": "audience_network",
                    "priority": "exclude" if (payload.get("cpa") or 0) > (payload.get("cpa_cible") or 999) else "low",
                    "rationale": "Souvent CPA plus élevé — à exclure si CPA critique.",
                },
            ],
        }

    def suggest_creatives(self, payload):
        raw = self._call(
            self.CREATIVE_SUGGESTION_SYSTEM,
            f"Contexte : {json.dumps(payload, ensure_ascii=False)}",
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
        )
        data = self._parse_json(raw)
        creatives = data.get("creatives") or []
        if creatives:
            return creatives
        return self._fallback_creatives(payload)

    def _fallback_creatives(self, payload):
        brand = payload.get("marque") or "Marque"
        action = payload.get("action") or ""
        valeur = payload.get("valeur") or "Découvrez notre offre"
        diff = payload.get("differentiateur") or ""
        canva_base = (
            f"Publicité Meta {brand} — {valeur[:80]}. "
            f"Style pro, couleurs marque, texte lisible mobile."
        )
        if action == "scale_down" or (payload.get("cpa") or 0) > (payload.get("cpa_cible") or 999):
            return [
                {
                    "format": "image",
                    "headline": f"{brand} — {(valeur or 'Offre')[:50]}",
                    "body": diff or f"{brand} : formulaire court, réponse rapide, sans engagement.",
                    "cta": "Découvrir l'offre",
                    "angle": "Offre directe",
                    "rationale": f"CPA élevé — simplifier le message autour de : {valeur[:80]}",
                    "canva_brief": canva_base,
                    "visual_description": f"Image statique — hero {brand}, CTA visible.",
                },
                {
                    "format": "video",
                    "headline": "Pourquoi choisir " + brand,
                    "body": diff or "Témoignage client — preuve sociale alignée sur la promesse de marque.",
                    "cta": "Voir les résultats",
                    "angle": "Preuve sociale",
                    "rationale": "Renforcer la confiance quand le coût par lead est trop élevé.",
                },
                {
                    "format": "carousel",
                    "headline": "3 raisons — " + brand,
                    "body": "1) Offre 2) Expertise 3) Accompagnement",
                    "cta": "En savoir plus",
                    "angle": "Éducation",
                    "rationale": "Carrousel pour améliorer le CTR avec l'offre détaillée.",
                },
            ]
        return [
            {
                "format": "image",
                "headline": (valeur or "")[:60],
                "body": diff or f"{brand} — offre adaptée à votre projet.",
                "cta": "Demander une soumission",
                "angle": "Proposition de valeur",
                "rationale": f"Créatif centré sur l'offre : {valeur[:80]}",
            },
            {
                "format": "image",
                "headline": brand + " — votre expert local",
                "body": diff or payload.get("cible") or "Accompagnement personnalisé.",
                "cta": "Parler à un expert",
                "angle": "Proximité",
                "rationale": "Aligné sur le persona et le différenciateur marque.",
            },
        ]

    WIZARD_BRIEF_SYSTEM = """Tu es l'assistant Traffic Manager Doorway (Intellix CRM).
L'utilisateur crée une campagne publicitaire en conversation multi-tours.
Collecte ces 4 éléments AVANT de mettre ready=true :
1. produit — quoi promouvoir (service, offre, produit)
2. cible — qui cibler (âge, profil, géo fine si pertinent)
3. budget — budget journalier (peut être pré-rempli)
4. objectif — leads, ventes, notoriété (souvent leads)

Règles :
- Pose UNE seule question précise par tour dans reply.
- Ne mets ready=true que si les 4 éléments sont clairs.
- Si message=[INIT], accueille brièvement et pose la première question (produit).
- Réponds UNIQUEMENT en JSON valide :
{
  "reply": "Question ou confirmation (2-4 phrases max)",
  "ready": false,
  "campaign_name": "Nom campagne suggéré",
  "budget_daily_suggested": 50,
  "summary": "Résumé cumulé du brief (mis à jour à chaque tour)",
  "checklist": {
    "produit": false,
    "cible": false,
    "budget": false,
    "objectif": false
  },
  "turn": 1
}"""

    def _wizard_brief_fallback(self, payload):
        """Filet de sécurité — questions séquentielles sans API."""
        msg = (payload.get("message") or "").strip()
        hist = payload.get("historique") or []
        user_turns = sum(1 for m in hist if m.get("role") == "user")
        budget = payload.get("budget_journalier") or 50
        checklist = {
            "produit": user_turns >= 1 and len(msg) > 5,
            "cible": user_turns >= 2,
            "budget": bool(budget),
            "objectif": True,
        }
        questions = [
            (
                f"Bonjour ! Campagne {payload.get('canal')} pour {payload.get('marque')} "
                f"({payload.get('zone')}). Quel produit ou service voulez-vous promouvoir ?"
            ),
            "Parfait. Qui est votre client idéal ? (âge, profil, situation)",
            f"Quel budget journalier confirmez-vous ? (suggestion : {budget} €/jour)",
            (
                "Merci — je résume et je prépare audiences + créatifs. "
                "Un dernier détail : angle prioritaire (urgence, subventions, preuve sociale) ?"
            ),
        ]
        if msg == "[INIT]":
            reply = questions[0]
            turn = 0
        else:
            turn = user_turns
            reply = questions[min(turn, len(questions) - 1)]
        ready = all(checklist.values()) and user_turns >= 3
        summary_parts = [m.get("text", "") for m in hist if m.get("role") == "user"]
        if msg and msg != "[INIT]":
            summary_parts.append(msg)
        return {
            "reply": reply,
            "ready": ready,
            "campaign_name": f"{payload.get('marque')} — {payload.get('canal')}",
            "budget_daily_suggested": budget,
            "summary": " · ".join(summary_parts)[:800],
            "checklist": checklist,
            "turn": turn + 1,
        }

    def wizard_campaign_brief(self, payload):
        hist = payload.get("historique") or []
        hist_txt = "\n".join(
            f"{m.get('role', 'user')}: {m.get('text', '')}" for m in hist[-12:]
        )
        prompt = (
            f"Marque : {payload.get('marque')}\n"
            f"Canal : {payload.get('canal')}\n"
            f"Zone : {payload.get('zone')} — objectif CPA "
            f"{payload.get('cpa_objectif')} {payload.get('devise')}/lead\n"
            f"Budget journalier déjà saisi : {payload.get('budget_journalier')} €\n"
            f"Historique ({len(hist)} messages) :\n{hist_txt}\n"
            f"Message utilisateur : {payload.get('message')}"
        )
        try:
            raw = self._call(
                self.WIZARD_BRIEF_SYSTEM,
                prompt,
                model="claude-haiku-4-5-20251001",
                max_tokens=900,
            )
            data = self._parse_json(raw)
        except Exception as exc:
            _logger.warning("Wizard brief Claude: %s", exc)
            data = None
        if not data:
            data = self._wizard_brief_fallback(payload)
        checklist = data.get("checklist") or {}
        if payload.get("budget_journalier"):
            checklist["budget"] = True
        checklist.setdefault("objectif", True)
        data["checklist"] = checklist
        if not data.get("summary") and hist:
            data["summary"] = " · ".join(
                m.get("text", "") for m in hist if m.get("role") == "user"
            )[:800]
        return data

    def generate_campaign_wizard(self, campaign, foundation, extra=None):
        """Génération campagne enrichie par le brief wizard."""
        extra = extra or {}
        payload = {
            "marque": foundation.brand_name,
            "strategie": foundation.brand_strategy,
            "differentiateur": foundation.differentiator,
            "objectif_campagne": campaign.objective or "leads",
            "canal": campaign.channel_id.name if campaign.channel_id else extra.get("canal", ""),
            "budget_total": campaign.budget_total,
            "budget_journalier": campaign.budget_daily,
            "brief_utilisateur": extra.get("brief_utilisateur") or campaign.optimization_brief,
            "zone": extra.get("zone"),
            "cpa_objectif": extra.get("cpa_objectif"),
            "devise": extra.get("devise"),
        }
        raw = self._call(
            CAMPAIGN_GENERATION_SYSTEM,
            f"Créer campagne (brief validé) : {json.dumps(payload, ensure_ascii=False)}",
        )
        data = self._parse_json(raw)
        if not data.get("audiences"):
            data = self._fallback_campaign(campaign, foundation)
        for aud in data.get("audiences", []):
            if not aud.get("targeting_rationale"):
                aud["targeting_rationale"] = aud.get("description") or ""
        return data

    def weekly_report(self, foundation, perf_summary):
        raw = self._call(
            WEEKLY_REPORT_SYSTEM,
            json.dumps(
                {"marque": foundation.brand_name, "performance": perf_summary},
                ensure_ascii=False,
            ),
            max_tokens=1500,
        )
        data = self._parse_json(raw)
        if not data:
            data = {
                "summary": f"Rapport hebdo — {foundation.brand_name}",
                "wins": perf_summary.get("wins", "—"),
                "concerns": perf_summary.get("concerns", "—"),
                "next_actions": "Valider les recommandations IA en attente.",
                "kpi_status": perf_summary.get("kpi_status", "—"),
            }
        return data
