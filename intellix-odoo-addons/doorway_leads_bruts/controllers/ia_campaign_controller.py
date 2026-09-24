# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request


class IaCampaignController(http.Controller):

    @http.route("/api/ia-campaign/callback", type="json", auth="public", methods=["POST"], csrf=False)
    def ia_campaign_callback(self, **kwargs):
        data = json.loads(request.httprequest.data)
        campaign_id = data.get("campaign_id")
        lead_id = data.get("lead_id")
        result = data.get("result")
        notes = data.get("notes", "")
        duration = data.get("duration_seconds", 0)

        if not campaign_id or not lead_id:
            return {"error": "missing_fields"}

        campaign = request.env["doorway.ia.campaign"].sudo().browse(campaign_id)
        if not campaign.exists():
            return {"error": "campaign_not_found"}

        # Mettre à jour stats campagne
        vals = {"leads_appeles": campaign.leads_appeles + 1}
        if result == "interesse":
            vals["leads_interesses"] = campaign.leads_interesses + 1
        elif result == "rappel":
            vals["leads_rappel"] = campaign.leads_rappel + 1
        elif result == "refus":
            vals["leads_refus"] = campaign.leads_refus + 1
        campaign.sudo().write(vals)

        # Mettre à jour le lead
        lead = request.env["doorway.leads.bruts"].sudo().browse(lead_id)
        if lead.exists():
            new_state = "qualifie" if result == "interesse" else lead.state
            lead_vals = {"state": new_state}
            # Le modèle n'expose pas de champ "notes_ia" : on retombe sur "notes".
            if "notes_ia" in lead._fields:
                lead_vals["notes_ia"] = notes
            elif notes:
                lead_vals["notes"] = notes
            lead.sudo().write(lead_vals)

        return {"status": "ok"}
