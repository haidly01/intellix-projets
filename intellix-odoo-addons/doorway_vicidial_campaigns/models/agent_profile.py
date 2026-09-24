# -*- coding: utf-8 -*-
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AgentProfileCampaign(models.Model):
    _inherit = "doorway.agent.profile"

    def _campaign_pipeline_for_agent(self):
        self.ensure_one()
        name = (self.name or "").lower()
        mapping = (
            ("thermo", "thermopompe"),
            ("ici therm", "thermopompe"),
            ("toiture", "toitures"),
            ("driven", "driven"),
            ("assurance", "assurance"),
            ("marketing", "marketing"),
        )
        for hint, pipeline in mapping:
            if hint in name:
                return pipeline
        if self.pipeline == "renovation":
            return "renovation"
        if self.pipeline == "immobilier":
            return "renovation"
        return "thermopompe" if self.energie_agent_role else "renovation"

    def action_go_live_from_web_test(self):
        """Valide l'agent en prod : sync prompt, campagne VICIdial, démarrage."""
        self.ensure_one()
        if not (self.system_prompt or "").strip():
            raise UserError(
                _("Prompt vide — enregistrez le script avant de passer en production.")
            )

        sync = self.sync_prompt_to_elevenlabs()
        if not sync.get("ok"):
            raise UserError(
                sync.get("message")
                or _("Synchronisation ElevenLabs impossible avant production.")
            )

        self.write({"status": "active", "wizard_step": "summary"})

        Campaign = self.env["doorway.campaign"]
        campaign = Campaign.search(
            [("ia_agent_id", "=", self.id)],
            order="create_date desc",
            limit=1,
        )
        vals = {
            "name": _("%s — Production") % self.name,
            "pipeline": self._campaign_pipeline_for_agent(),
            "ia_agent_id": self.id,
            "campaign_mode": "ia_agent",
            "ia_call_script_hint": (self.system_prompt or "")[:2000],
        }
        if campaign:
            campaign.write({**vals, "state": "ready"})
        else:
            campaign = Campaign.create({**vals, "state": "ready"})

        vicidial_msg = ""
        started = False
        try:
            campaign.action_sync_vicidial()
        except Exception as exc:  # noqa: BLE001
            vicidial_msg = str(exc)
            _logger.warning("Sync VICIdial avant prod agent %s: %s", self.id, exc)

        try:
            campaign.action_start()
            started = True
        except Exception as exc:  # noqa: BLE001
            vicidial_msg = vicidial_msg or str(exc)
            _logger.warning("Start campagne agent %s: %s", self.id, exc)

        action = campaign.action_open_dashboard()
        return {
            "ok": True,
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "campaign_state": campaign.state,
            "started": started,
            "vicidial_message": vicidial_msg,
            "elevenlabs_agent_id": self.external_agent_id,
            "action": action,
        }
