# -*- coding: utf-8 -*-
from odoo import _, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def action_send_whatsapp(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("WhatsApp"),
            "res_model": "doorway.whatsapp.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_phone": self.phone,
            },
        }
