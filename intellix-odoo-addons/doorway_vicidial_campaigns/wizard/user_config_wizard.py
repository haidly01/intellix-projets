# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class DoorwayUserConfigWizard(models.TransientModel):
    _name = "doorway.user.config.wizard"
    _description = "Configurer agents humains campagne"

    campaign_id = fields.Many2one("doorway.campaign", required=True)
    user_ids = fields.Many2many(
        "res.users",
        required=True,
        domain="[('is_human_call_agent', '=', True)]",
    )
    user_group = fields.Char(default="AGENTS")
    user_level = fields.Integer(default=1)
    sync_vicidial = fields.Boolean(default=True)

    def action_apply(self):
        self.ensure_one()
        if not self.user_ids:
            raise UserError(_("Sélectionnez au moins un utilisateur."))
        self.campaign_id.with_context(
            human_agent_user_group=self.user_group,
            human_agent_user_level=self.user_level,
            sync_human_agent_vicidial=self.sync_vicidial,
        ).write({"human_agent_user_ids": [(6, 0, self.user_ids.ids)]})
        return {"type": "ir.actions.act_window_close"}
