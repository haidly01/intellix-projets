# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayCampaignAgentsIa(models.Model):
    _inherit = "doorway.campaign"

    agent_id = fields.Many2one("doorway.agent.ia", string="Agent IA lié (legacy)")
    lead_count = fields.Integer(compute="_compute_lead_count")

    def _compute_lead_count(self):
        if "crm.lead" not in self.env:
            for rec in self:
                rec.lead_count = 0
            return
        Lead = self.env["crm.lead"]
        for rec in self:
            domain = []
            if rec.vicidial_campaign_id:
                domain.append(("vicidial_campaign_id", "=", rec.vicidial_campaign_id))
            rec.lead_count = Lead.search_count(domain)
