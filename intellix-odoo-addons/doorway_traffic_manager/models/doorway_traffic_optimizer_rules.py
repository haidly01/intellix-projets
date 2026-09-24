# -*- coding: utf-8 -*-
"""Règles d'optimisation déterministes (sans LLM) — lisibles et actionnables."""
from odoo import _, api, models


class DoorwayTrafficOptimizerRules(models.AbstractModel):
    _name = "doorway.traffic.optimizer.rules"
    _description = "Règles optimisation Traffic Manager"

    @api.model
    def apply_to_campaign(self, campaign):
        campaign.ensure_one()
        foundation = campaign.foundation_id
        target_cpa = (
            campaign.optimization_target_cpa
            or foundation.target_cpa_eur
            or 0
        )
        target_ctr = 1.0
        spend = campaign.spend or 0
        spend_30d = campaign.spend_30d or 0
        conv = campaign.conversions or 0
        conv_30d = campaign.conversions_30d or 0
        cpa = campaign.cpa or 0
        cpa_30d = campaign.cpa_30d or 0
        ctr = campaign.ctr or 0
        effective_spend = spend_30d if spend_30d > spend else spend
        effective_conv = conv_30d if spend_30d > spend else conv
        effective_cpa = cpa_30d if spend_30d > spend and conv_30d else cpa
        ext_id = (campaign.external_campaign_id or "").strip()
        meta_name = campaign.meta_campaign_name or ""

        health = "good"
        action = "none"
        summary = ""
        recommendation = ""

        if not ext_id:
            health = "unlinked"
            action = "fix_link"
            summary = _("Campagne Meta non liée — aucune sync possible.")
            recommendation = _(
                "Cliquez « Corriger liens Meta » ou renseignez external_campaign_id "
                "avec l'ID campagne ACTIVE sur Meta Ads Manager."
            )
        elif spend <= 0 and spend_30d <= 0:
            health = "warning"
            action = "scale_up"
            summary = _("0€ dépensé sur 7j et 30j — aucune diffusion récente.")
            recommendation = _(
                "Vérifiez budget journalier et statut ad sets sur Meta Ads Manager."
            )
        elif spend <= 0 and spend_30d > 0:
            health = "warning"
            action = "new_creative"
            summary = _(
                "%.0f€ sur 30j mais 0€ cette semaine — reprise ou baisse d'activité."
            ) % spend_30d
            recommendation = _(
                "Relancer la campagne ou tester un nouveau créatif pour retrouver "
                "le rythme (30j : %s leads, CPA %.0f€)."
            ) % (conv_30d, cpa_30d or 0)
        elif effective_conv <= 0 and effective_spend > 20:
            health = "critical"
            action = "new_creative"
            summary = _(
                "%.0f€ dépensés, 0 lead — le funnel ne convertit pas."
            ) % effective_spend
            recommendation = _(
                "Tester un nouveau créatif + revoir le formulaire Lead Ads. "
                "Envisager pause si pas de correction sous 48h."
            )
        elif target_cpa and effective_cpa > target_cpa * 1.2:
            health = "critical"
            action = "scale_down"
            ratio = int(100 * effective_cpa / target_cpa)
            summary = _("CPA %.0f€ — %s%% au-dessus de la cible (%.0f€).") % (
                effective_cpa, ratio, target_cpa
            )
            recommendation = _(
                "Réduire le budget journalier de 25%% et lancer un test créatif. "
                "CTR 7j : %.2f%% · Dépense 30j : %.0f€."
            ) % (ctr, spend_30d)
        elif target_cpa and effective_cpa > target_cpa:
            health = "warning"
            action = "new_creative"
            summary = _("CPA %.0f€ — légèrement au-dessus de la cible %.0f€.") % (
                cpa, target_cpa
            )
            recommendation = _(
                "Optimiser le ciblage ou le créatif avant d'augmenter le budget."
            )
        elif ctr < target_ctr and spend > 30:
            health = "warning"
            action = "new_creative"
            summary = _("CTR %.2f%% — sous le seuil %.1f%%.") % (ctr, target_ctr)
            recommendation = _(
                "Remplacer l'accroche visuelle / texte pub pour améliorer le clic."
            )
        elif target_cpa and cpa <= target_cpa * 0.8 and conv >= 3:
            health = "excellent"
            action = "scale_up"
            summary = _("CPA %.0f€ — sous la cible. %s leads sur 7j.") % (cpa, conv)
            recommendation = _(
                "Performance saine : vous pouvez augmenter le budget de 25%% "
                "après validation."
            )
        else:
            health = "good"
            action = "none"
            summary = _(
                "Performance dans les clous — %s leads, CPA %.0f€, CTR %.2f%%."
            ) % (conv, cpa, ctr)
            recommendation = _("Maintenir et surveiller. Prochaine sync dans 6h.")

        vals = {
            "optimization_health": health,
            "optimization_summary": summary,
        }
        if not campaign.optimization_customized:
            vals["ai_action_pending"] = action if action != "none" else "none"
            vals["ai_recommendation"] = recommendation
        campaign.write(vals)
        return {"health": health, "action": action, "summary": summary}

    @api.model
    def apply_to_all_active(self):
        campaigns = self.env["doorway.traffic.campaign"].search([
            ("ai_status", "in", ["active", "approved", "paused"]),
        ])
        for campaign in campaigns:
            self.apply_to_campaign(campaign)
        return len(campaigns)
