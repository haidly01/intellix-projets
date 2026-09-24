# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class CoinsQuebecRdvRejectWizard(models.TransientModel):
    _name = "coins.quebec.rdv.reject.wizard"
    _description = "Rejeter un RDV Coins Québec"

    rdv_id = fields.Many2one("coins.quebec.rdv", required=True, ondelete="cascade")
    reject_note = fields.Text(string="Motif du rejet", required=True)

    def action_reject(self):
        self.ensure_one()
        rdv = self.rdv_id
        if not rdv._cq_user_is_martin() and not self.env.su:
            raise AccessError(_("Seul Martin peut rejeter un RDV."))
        if rdv.martin_state != "pending":
            raise UserError(_("Ce RDV n'est plus en attente de validation."))
        note = (self.reject_note or "").strip()
        if not note:
            raise UserError(_("Indiquez le motif du rejet."))
        rdv.write(
            {
                "martin_state": "rejected",
                "reject_note": note,
                "validated_at": fields.Datetime.now(),
            }
        )
        return {"type": "ir.actions.act_window_close"}
