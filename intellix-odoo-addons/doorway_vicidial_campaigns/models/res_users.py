# -*- coding: utf-8 -*-
from odoo import api, fields, models

HUMAN_CALL_AGENT_GROUP_XMLIDS = (
    "doorway_vicidial_campaigns.group_vicidial_qualifier",
    "doorway_vicidial_campaigns.group_vicidial_supervisor",
    "doorway_agents_dashboard.group_doorway_agent_viewer",
    "doorway_agents_dashboard.group_doorway_agent_tester",
    "doorway_agents_dashboard.group_doorway_agent_manager",
    "doorway_demo_call_center.group_demo_call_center",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    is_human_call_agent = fields.Boolean(
        string="Agent humain appels",
        compute="_compute_is_human_call_agent",
        search="_search_is_human_call_agent",
        help="Utilisateur éligible à l'assignation sur une campagne d'appels humains.",
    )

    @api.model
    def _human_call_agent_group_ids(self):
        group_ids = []
        for xmlid in HUMAN_CALL_AGENT_GROUP_XMLIDS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
        return group_ids

    @api.depends("group_ids")
    def _compute_is_human_call_agent(self):
        eligible_ids = set(self._human_call_agent_group_ids())
        Agent = self.env["doorway.campaign.agent.user"]
        for user in self:
            in_group = bool(eligible_ids & set(user.group_ids.ids))
            has_agent = bool(
                Agent.search_count([("user_id", "=", user.id)], limit=1)
            )
            user.is_human_call_agent = user.active and not user.share and (
                in_group or has_agent
            )

    def _search_is_human_call_agent(self, operator, value):
        if operator not in ("=", "!="):
            return []
        want = operator == "=" and bool(value)
        eligible = self.search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("group_ids", "in", self._human_call_agent_group_ids()),
            ]
        )
        Agent = self.env["doorway.campaign.agent.user"]
        linked = Agent.search([]).mapped("user_id")
        matched = (eligible | linked).filtered(lambda u: u.active and not u.share)
        if want:
            return [("id", "in", matched.ids)]
        return [("id", "not in", matched.ids)]
