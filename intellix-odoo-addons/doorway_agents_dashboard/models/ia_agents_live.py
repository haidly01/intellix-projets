# -*- coding: utf-8 -*-
from odoo import api, models


class IaAgentsLive(models.AbstractModel):
    _name = "doorway.ia.agents.live"
    _description = "Monitoring live agents IA (Sofia FR + Léa QC)"

    @api.model
    def get_snapshot(self, live=False):
        from ..services.ia_agents_live_service import IaAgentsLiveService

        return IaAgentsLiveService(self.env).build_snapshot(live=live)

    @api.model
    def refresh_snapshot(self):
        return self.get_snapshot(live=True)
