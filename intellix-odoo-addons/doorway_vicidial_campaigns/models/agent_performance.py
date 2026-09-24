# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AgentProfileCampaignPerformance(models.Model):
    _inherit = "doorway.agent.profile"

    campaign_ids = fields.Many2many(
        "doorway.campaign",
        compute="_compute_campaign_ids",
        search="_search_campaign_ids",
        string="Campagnes",
    )
    campagne_active_ids = fields.Many2many(
        "doorway.campaign",
        compute="_compute_campagne_active_ids",
        string="Campagnes actives (liste)",
    )
    production_call_log_ids = fields.Many2many(
        "doorway.call.log",
        compute="_compute_production_call_log_ids",
        string="Appels production",
    )

    @api.depends("status")
    def _compute_campaign_ids(self):
        Campaign = self.env["doorway.campaign"]
        for agent in self:
            agent.campaign_ids = Campaign.search([("ia_agent_id", "=", agent.id)])

    @api.depends("status")
    def _compute_campagne_active_ids(self):
        Campaign = self.env["doorway.campaign"]
        for agent in self:
            agent.campagne_active_ids = Campaign.search(
                [
                    ("ia_agent_id", "=", agent.id),
                    ("state", "=", "active"),
                ]
            )

    def _compute_production_call_log_ids(self):
        for agent in self:
            agent.production_call_log_ids = agent._production_call_logs()

    @api.model
    def _search_campaign_ids(self, operator, value):
        Campaign = self.env["doorway.campaign"]
        if operator in ("ilike", "like", "=", "child_of"):
            camps = Campaign.search(
                [
                    "|",
                    ("name", operator, value),
                    ("vicidial_campaign_id", operator, value),
                ]
            )
            return [("id", "in", camps.mapped("ia_agent_id").ids)]
        if operator == "in" and value:
            camps = Campaign.browse(value)
            return [("id", "in", camps.mapped("ia_agent_id").ids)]
        return []
