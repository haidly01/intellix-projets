# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class DoorwayCampagneExtraction(models.Model):
    _inherit = "doorway.campagne.extraction"

    def action_import_callcenter_prospects(self):
        self.ensure_one()
        if self.zone_geographique not in ("maroc", "tunisie"):
            raise UserError(_("Cette campagne n'est pas Maroc/Tunisie."))
        result = (
            self.env["doorway.callcenter.prospect"]
            .sudo()
            .import_from_leads_bruts(self.id)
        )
        message = _(
            "Import prospects : %(created)s créés, %(dupes)s doublons, %(invalid)s invalides."
        ) % result
        self.message_post(body=message, message_type="notification")
        return {
            "type": "ir.actions.act_window",
            "name": _("Prospects Call Center"),
            "res_model": "doorway.callcenter.prospect",
            "view_mode": "list,form",
            "domain": [("extraction_campaign_id", "=", self.id)],
        }
