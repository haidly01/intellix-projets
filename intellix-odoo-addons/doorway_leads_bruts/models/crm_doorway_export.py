# -*- coding: utf-8 -*-
"""Export des leads bruts vers le pipeline Marketing Doorway (Zakaria)."""
from odoo import _, api, models

DOORWAY_MARKETING_ASSIGNEE = "zakaria@agencedoorway.com"
DOORWAY_MARKETING_TEAM_XMLID = "renovation_conciergerie.crm_team_marketing"


class DoorwayLeadsBrutsCrmExport(models.AbstractModel):
    _name = "doorway.leads.bruts.crm.export"
    _description = "Export Extracteur → CRM Marketing Doorway"

    @api.model
    def _marketing_team(self):
        return self.env.ref(DOORWAY_MARKETING_TEAM_XMLID, raise_if_not_found=False)

    @api.model
    def _resolve_assignee(self, login=None):
        login = (login or DOORWAY_MARKETING_ASSIGNEE).strip()
        user = self.env["res.users"].sudo().search(
            [("login", "=", login), ("active", "=", True)],
            limit=1,
        )
        if user:
            return user
        team = self._marketing_team()
        return team._get_default_assignee() if team else self.env["res.users"]

    @api.model
    def _marketing_company_id(self, assignee):
        Team = self.env["crm.team"]
        digital_id = Team._doorway_digital_doorway_company_id()
        if digital_id:
            return digital_id
        if assignee and assignee.company_id:
            return assignee.company_id.id
        team = self._marketing_team()
        if team and team.company_id:
            return team.company_id.id
        return False

    @api.model
    def prepare_crm_vals_from_lead_brut(self, lead_brut):
        """Construit les vals crm.lead pour le pipeline Marketing / Zakaria."""
        team = self._marketing_team()
        if not team:
            raise ValueError(_("Pipeline Marketing Doorway introuvable."))

        config = self.env["doorway.credit.config"].get_config()
        assignee = self._resolve_assignee(config.crm_assignee_login)
        campagne = lead_brut.campagne_id
        source_label = lead_brut.source_id.name or lead_brut.source_key or "source inconnue"

        desc_lines = [
            "Source: IntelliX Extracteur (scraping B2B).",
            "Pipeline: Marketing Doorway — assigné à Zakaria.",
            f"Campagne: {campagne.name}" if campagne else "",
            f"Mot-clé: {campagne.mot_cle}" if campagne and campagne.mot_cle else "",
            f"Zone: {campagne.ville_region}" if campagne and campagne.ville_region else "",
            f"Source web: {source_label}",
        ]
        if lead_brut.source_url:
            desc_lines.append(f"URL: {lead_brut.source_url}")
        if lead_brut.notes:
            desc_lines.append(f"Notes: {lead_brut.notes}")

        lead_name = lead_brut.name
        if campagne and campagne.mot_cle:
            lead_name = f"{campagne.mot_cle} — {lead_brut.name}"

        vals = {
            "name": f"Extracteur — {lead_name}",
            "type": "opportunity",
            "team_id": team.id,
            "lead_provenance": "nouveau",
            "contact_name": lead_brut.name,
            "phone": lead_brut.phone or False,
            "email_from": lead_brut.email or False,
            "website": lead_brut.website or False,
            "street": lead_brut.address or False,
            "city": lead_brut.city or False,
            "description": "\n".join(line for line in desc_lines if line),
        }
        if assignee:
            vals["user_id"] = assignee.id
        company_id = self._marketing_company_id(assignee)
        if company_id:
            vals["company_id"] = company_id
        return vals

    @api.model
    def reassign_marketing_extracteur_leads(self):
        """Réassigne à Zakaria les opportunités Marketing liées à l'Extracteur."""
        team = self._marketing_team()
        assignee = self._resolve_assignee()
        if not team or not assignee:
            return 0

        LeadsBruts = self.env["doorway.leads.bruts"].sudo()
        linked = LeadsBruts.search([("crm_lead_id", "!=", False)]).mapped(
            "crm_lead_id"
        )
        to_fix = linked.filtered(
            lambda lead: lead.team_id == team
            and lead.user_id != assignee
            and lead.active
        )
        if not to_fix:
            return 0
        to_fix.sudo().write({"user_id": assignee.id})
        return len(to_fix)
