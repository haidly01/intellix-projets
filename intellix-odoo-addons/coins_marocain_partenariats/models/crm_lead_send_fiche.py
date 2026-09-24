# -*- coding: utf-8 -*-
from odoo import models, _


class CrmLeadSendFiche(models.Model):
    _inherit = "crm.lead"

    def action_coins_envoyer_fiche(self):
        """Ouvre le wizard mauve : courriel + maquette, destinataire = email de la fiche."""
        self.ensure_one()
        self._coins_ensure_partner_property()
        email = (self.email_from or "").strip()
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer la fiche"),
            "res_model": "coins.send.fiche.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.id,
                "default_email_to": email,
                "default_test_mode": False,
            },
        }
