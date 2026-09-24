# -*- coding: utf-8 -*-
from odoo import api, models

from .service_label_map import collect_service_labels, map_service_label


class RenoImmobilierWebsiteLeadWebhook(models.AbstractModel):
    _inherit = "renovation.website.lead.webhook"

    @api.model
    def _reno_quebec_state(self):
        return self.env["res.country.state"].sudo().search(
            [("code", "=", "QC"), ("country_id.code", "=", "CA")],
            limit=1,
        )

    @api.model
    def _reno_resolve_service_categories(self, data):
        names = []
        for label in collect_service_labels(data):
            mapped = map_service_label(label)
            if mapped:
                names.append(mapped)
        if not names:
            return self.env["renovation.service.category"]
        Category = self.env["renovation.service.category"].sudo()
        found = Category.browse()
        for name in dict.fromkeys(names):
            cat = Category.search([("name", "=ilike", name)], limit=1)
            if cat:
                found |= cat
        return found

    @api.model
    def create_lead_from_website_payload(self, pipeline_key, data):
        data = dict(data or {})
        categories = self._reno_resolve_service_categories(data)
        if categories:
            data["services"] = categories.mapped("name")
        result, code = super().create_lead_from_website_payload(pipeline_key, data)
        if code != 200 or not result.get("lead_id"):
            return result, code
        lead = self.env["crm.lead"].sudo().browse(result["lead_id"])
        if not lead.exists():
            return result, code
        vals = {}
        if not lead.state_id and lead.city:
            qc = self._reno_quebec_state()
            if qc:
                vals["state_id"] = qc.id
        if categories and not lead.service_category_ids:
            vals["service_category_ids"] = [(6, 0, categories.ids)]
        labels = getattr(self, "SITE_SOURCE_LABELS", {}) or {}
        site = (
            data.get("site_source")
            or data.get("site")
            or data.get("source_site")
            or ""
        ).strip()
        if not site:
            site = lead._reno_site_source_from_notes()
        site_l = site.lower().replace("www.", "").split("/")[0].strip()
        wanted_label = (
            data.get("source_label")
            or labels.get(site_l)
            or (lead.source_id.name if lead.source_id else "")
        )
        visitor_source = (data.get("utm_source") or "").strip()
        # Attribution visiteur (UTM / Direct / Organique…) prime sur l'étiquette site.
        if visitor_source:
            wanted_label = False
        elif site_l in labels and (lead.source_id.name or "") != labels[site_l]:
            wanted_label = labels[site_l]
        if wanted_label:
            ensure = getattr(self, "_ensure_utm_source", None)
            source = ensure(wanted_label) if callable(ensure) else False
            if source and lead.source_id != source:
                vals["source_id"] = source.id
        gestion = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        doorway = self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )
        if site_l in getattr(self, "DOORWAY_SITES", set()) and doorway:
            if lead.team_id != doorway:
                vals["team_id"] = doorway.id
        elif gestion and lead.team_id != gestion and site_l not in getattr(
            self, "BLOCKED_SITES", set()
        ) and site_l not in getattr(self, "DOORWAY_SITES", set()):
            if lead.team_id.id in set(lead._reno_immo_team_ids()) or not lead.team_id:
                vals["team_id"] = gestion.id
        if gestion and gestion.company_id and not lead.company_id:
            vals["company_id"] = gestion.company_id.id
        if vals:
            lead.write(vals)
        if (
            lead.service_category_ids
            and not lead.reno_assigned_partner_id
            and lead.assignment_status in ("pending", "no_match", False, None)
        ):
            if hasattr(lead, "action_assign_partner"):
                lead.action_assign_partner()
        return result, code
