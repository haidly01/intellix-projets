# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AgentProfile(models.Model):
    _inherit = "doorway.agent.profile"

    company_id = fields.Many2one(
        "res.company",
        string="Société",
        index=True,
        default=lambda self: self.env.company,
        help="Société propriétaire (isolation demo call center).",
    )

    @api.model
    def _demo_agent_domain(self):
        user = self.env.user
        return [("company_id", "in", user.company_ids.ids)]

    @api.model
    def action_demo_open_my_agent(self):
        """Ouvre le wizard de l'agent IA demo (ex. Sofía) ou la liste si plusieurs."""
        if not self.env.user.demo_call_center:
            raise UserError(_("Réservé aux comptes Demo Call Center."))
        agents = self.search(self._demo_agent_domain(), order="id asc")
        if not agents:
            raise UserError(
                _(
                    "Aucun agent IA n'est configuré pour votre espace demo. "
                    "Contactez le support Intellix."
                )
            )
        if len(agents) == 1:
            return agents.action_open_edit_wizard()
        return {
            "type": "ir.actions.act_window",
            "name": _("Mes agents IA"),
            "res_model": "doorway.agent.profile",
            "view_mode": "list,form",
            "domain": self._demo_agent_domain(),
            "context": {"default_company_id": self.env.company.id},
        }

    def action_demo_open_performance(self):
        """Dashboard performance de l'agent IA demo (Sofía)."""
        if not self.env.user.demo_call_center:
            raise UserError(_("Réservé aux comptes Demo Call Center."))
        agent = self[:1] if self else self.search(
            self._demo_agent_domain(), order="id asc", limit=1
        )
        if not agent:
            raise UserError(_("Aucun agent IA configuré."))
        agent.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "performance_dashboard_action",
            "name": _("Performance — %s") % agent.name,
            "context": {"default_agent_id": agent.id},
            "params": {"agent_id": agent.id},
        }

    def performance_agent_detail(self, period_days=30, call_page=1, page_size=20):
        self.ensure_one()
        res = super().performance_agent_detail(
            period_days=period_days, call_page=call_page, page_size=page_size
        )
        if not self.env.user.demo_call_center:
            return res
        camp = self.env["doorway.campaign"].search(
            [("ia_agent_id", "=", self.id)], limit=1
        )
        if camp:
            breakdown = self.env[
                "doorway.campaign"
            ].browse(camp.id)._vicidial_svc().get_call_breakdown(
                camp, days=period_days
            )
            res["call_breakdown"] = {
                "total": breakdown.get("total", 0),
                "human": breakdown.get("human", 0),
                "repondeur": breakdown.get("repondeur", 0),
                "mauvais_numero": breakdown.get("mauvais_numero", 0),
                "sans_reponse": breakdown.get("sans_reponse", 0),
                "occupe": breakdown.get("occupe", 0),
                "qualifie": breakdown.get("qualifie", 0),
            }
        return res

    @api.model
    def performance_list_agents(self, filters=None):
        res = super().performance_list_agents(filters=filters)
        if not self.env.user.demo_call_center:
            return res
        allowed = set(self.search(self._demo_agent_domain()).ids)
        res["agents"] = [
            row for row in res.get("agents", []) if row.get("id") in allowed
        ]
        Campaign = self.env.get("doorway.campaign")
        if Campaign:
            res["campaigns"] = [
                {
                    "id": c.id,
                    "name": c.name,
                    "vicidial_id": c.vicidial_campaign_id,
                }
                for c in Campaign.search(
                    [("company_id", "in", self.env.user.company_ids.ids)]
                )
            ]
        return res

    def action_view_demo_call_logs(self):
        """Journal des appels production liés aux campagnes de l'agent."""
        self.ensure_one()
        campaigns = self.env["doorway.campaign"].search(
            [("ia_agent_id", "=", self.id)]
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Appels — %s") % self.name,
            "res_model": "doorway.call.log",
            "view_mode": "list,form",
            "domain": [("campaign_id", "in", campaigns.ids)],
        }

