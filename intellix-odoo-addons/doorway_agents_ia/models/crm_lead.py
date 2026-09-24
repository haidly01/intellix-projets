# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    vicidial_campaign_id = fields.Char(string="Campagne VICIdial", index=True)
    doorway_call_session_ids = fields.One2many(
        "doorway.call.session", "lead_id", string="Sessions d'appel IA"
    )

    def action_assign_vicidial_campaign(self):
        """Assigne le lead à la campagne VICIdial selon le pipeline."""
        Campaign = self.env["doorway.campaign"]
        from odoo.addons.doorway_agents_ia.services.vicidial_service import VicidialService as VS

        pipeline_map = {
            "Rénovation": "renovation",
            "Driven": "driven",
            "Marketing": "marketing",
            "Assurance": "assurance",
        }
        svc = VS(self.env)
        for lead in self:
            pipeline = pipeline_map.get(lead.team_id.name or "", "renovation")
            campaign = Campaign.search(
                [("pipeline", "=", pipeline), ("active", "=", True)], limit=1
            )
            if not campaign:
                continue
            lead_data = {
                "phone": lead.phone or lead.mobile or "",
                "first_name": lead.contact_name or lead.name or "",
                "last_name": "",
                "vendor_code": "LEAD-%s" % lead.id,
            }
            if svc.assign_lead_to_campaign(lead_data, campaign.vicidial_campaign_id):
                lead.vicidial_campaign_id = campaign.vicidial_campaign_id
