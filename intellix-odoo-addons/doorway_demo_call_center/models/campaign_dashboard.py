# -*- coding: utf-8 -*-
from odoo import api, models


class DoorwayCampaign(models.Model):
    _inherit = "doorway.campaign"

    @api.model
    def dashboard_list_campaigns(self, filters=None):
        result = super().dashboard_list_campaigns(filters=filters)
        user = self.env.user
        if not user.demo_call_center:
            return result
        allowed = set(
            self.search([("company_id", "in", user.company_ids.ids)]).ids
        )
        campaigns = [row for row in result.get("campaigns", []) if row["id"] in allowed]
        allowed_agents = set(
            self.env["doorway.agent.profile"]
            .search([("company_id", "in", user.company_ids.ids)])
            .ids
        )
        agents = [a for a in result.get("agents", []) if a["id"] in allowed_agents]
        summary = dict(result.get("summary") or {})
        summary["active_campaigns"] = len(
            [c for c in campaigns if c.get("state") == "active"]
        )
        summary["total_contacts"] = sum(c.get("total_contacts") or 0 for c in campaigns)
        return {
            **result,
            "campaigns": campaigns,
            "agents": agents,
            "summary": summary,
        }
