# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LeadAutomationHub(models.Model):
    _name = "lead.automation.hub"
    _description = "Lead Automation Hub — accueil"

    name = fields.Char(default="Lead Automation Hub", required=True)
    campaign_map_count = fields.Integer(compute="_compute_counts")
    lead_count = fields.Integer(compute="_compute_counts")

    @api.depends()
    def _compute_counts(self):
        map_count = self.env["lead.campaign.map"].search_count([])
        lead_count = self.env["crm.lead"].search_count([])
        for rec in self:
            rec.campaign_map_count = map_count
            rec.lead_count = lead_count

    @api.model
    def _get_hub(self):
        hub = self.search([], limit=1)
        if not hub:
            hub = self.create({"name": "Lead Automation Hub"})
        return hub

    @api.model
    def action_open_home(self):
        hub = self._get_hub()
        view = self.env.ref(
            "lead_automation_hub.view_lead_automation_hub_dashboard",
            raise_if_not_found=False,
        )
        action = {
            "type": "ir.actions.act_window",
            "name": "Lead Automation Hub",
            "res_model": "lead.automation.hub",
            "res_id": hub.id,
            "view_mode": "form",
            "target": "current",
        }
        if view:
            action["views"] = [(view.id, "form")]
            action["view_id"] = view.id
        return action

    def action_open_campaign_maps(self):
        return self.env.ref("lead_automation_hub.action_lead_campaign_map").read()[0]

    def action_open_leads(self):
        return self.env.ref("crm.crm_lead_all_leads").read()[0]
