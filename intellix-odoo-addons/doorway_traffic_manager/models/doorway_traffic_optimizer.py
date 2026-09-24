# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DoorwayTrafficOptimizer(models.AbstractModel):
    _name = "doorway.traffic.optimizer"
    _description = "Moteur optimisation Traffic Manager"

    @api.model
    def cron_daily_optimization(self):
        today = fields.Date.today()
        campaigns = self.env["doorway.traffic.campaign"].search([
            ("ai_status", "=", "active"),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", today),
        ])
        for campaign in campaigns:
            try:
                self._analyze_campaign(campaign)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Optimisation campagne %s: %s", campaign.id, exc
                )
        return True

    def _analyze_campaign(self, campaign):
        foundation = campaign.foundation_id
        perf_data = {
            "nom": campaign.name,
            "canal": campaign.channel_id.name if campaign.channel_id else "",
            "objectif": campaign.objective,
            "budget_jour": campaign.budget_daily,
            "depense": campaign.spend,
            "impressions": campaign.impressions,
            "clics": campaign.clicks,
            "ctr": campaign.ctr,
            "conversions": campaign.conversions,
            "cpa_actuel": campaign.cpa,
            "cpa_cible": foundation.target_cpa_eur,
            "roas_actuel": campaign.roas,
            "roas_cible": foundation.target_roas,
            "audiences": [
                {
                    "nom": a.name,
                    "ctr": a.ctr,
                    "cpa": a.cpa,
                    "freq": a.frequency,
                }
                for a in campaign.audience_ids
                if a.ai_status == "active"
            ],
            "creatifs": [
                {"format": c.format, "ctr": c.ctr, "cpa": c.cpa}
                for c in campaign.creative_ids
                if c.ai_status == "active"
            ],
        }

        result = self.env["doorway.traffic.claude.service"].optimize_campaign(
            perf_data
        )

        campaign.write({
            "ai_recommendation": "%s — %s" % (
                result.get("diagnostic", ""),
                result.get("action_reason", ""),
            ),
            "ai_action_pending": result.get("action_priority") or "none",
        })

        if result.get("action_priority") and result["action_priority"] != "none":
            assignee = campaign.pipeline_id.user_id
            if assignee:
                campaign.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary="⚡ Traffic Manager : %s" % result.get(
                        "action_reason", "Recommandation IA"
                    ),
                    note=result.get("action_detail") or "",
                    user_id=assignee.id,
                )

        self._optimize_audiences(campaign, result)

        if (
            foundation.allow_auto_pause
            and foundation.monthly_budget_eur
            and campaign.spend > foundation.monthly_budget_eur
        ):
            campaign.write({"ai_status": "paused"})
            campaign.message_post(
                body="Campagne mise en pause automatiquement — dépassement budget mensuel.",
            )

    def _optimize_audiences(self, campaign, ai_result):
        Audience = self.env["doorway.audience"]
        foundation = campaign.foundation_id

        for audience_name in ai_result.get("audiences_to_pause") or []:
            audience = campaign.audience_ids.filtered(
                lambda a: a.name == audience_name
            )
            if audience:
                audience.write({"ai_status": "proposed"})

        winner_audiences = campaign.audience_ids.filtered(
            lambda a: a.ai_status == "active"
            and a.cpa > 0
            and foundation.target_cpa_eur
            and a.cpa < foundation.target_cpa_eur
        )
        if winner_audiences:
            winner = winner_audiences[0]
            Audience.create({
                "campaign_id": campaign.id,
                "name": "Lookalike — %s" % winner.name,
                "audience_type": "lookalike",
                "source": "ai_generated",
                "ai_status": "proposed",
                "description": (
                    "Lookalike 1-3 %% généré depuis %s (CPA sous objectif)."
                    % winner.name
                ),
                "platform": winner.platform,
            })
