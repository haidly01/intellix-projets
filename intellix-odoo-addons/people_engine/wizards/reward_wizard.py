# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class PeopleEngineRewardWizard(models.TransientModel):
    _name = "pe.reward.wizard"
    _description = "Attribution récompense People Engine"

    profile_id = fields.Many2one("pe.employee.profile", required=True)
    reward_id = fields.Many2one("pe.reward", required=True)
    note = fields.Text()
    dg_approved = fields.Boolean(string="Approbation DG confirmée")

    def action_grant(self):
        self.ensure_one()
        reward = self.reward_id
        if reward.dg_approval_required and not self.dg_approved:
            raise UserError(
                _("Cette récompense requiert l'approbation de la direction générale.")
            )
        self.env["pe.action.log"].log_action(
            self.profile_id,
            "praise_sent",
            _("Récompense « %s » attribuée : %s")
            % (reward.name, self.note or ""),
            actor_type="hr",
        )
        if reward.reward_type == "recognition" and self.profile_id.user_id.partner_id:
            self.profile_id.message_post(
                body=_("Récompense : %s — %s")
                % (reward.name, self.note or ""),
                partner_ids=[self.profile_id.user_id.partner_id.id],
            )
        return {"type": "ir.actions.act_window_close"}
