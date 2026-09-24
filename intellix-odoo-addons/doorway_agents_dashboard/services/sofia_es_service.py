# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


class SofiaEsService:
    """Post-appel Sofia Espagne — tags partenaire + lead CRM."""

    def __init__(self, env):
        self.env = env

    def _get_or_create_tag(self, name):
        Category = self.env["res.partner.category"].sudo()
        tag = Category.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Category.create({"name": name})
        return tag

    def process_call_ended(self, data, company_id=False):
        data = data or {}
        partner = self.env["res.partner"].sudo().browse(int(data.get("partner_id") or 0))
        if not partner.exists() and data.get("telephone"):
            phone = (data.get("telephone") or "").replace(" ", "")[-9:]
            domain = [
                "|",
                ("phone", "ilike", phone),
                ("phone_sanitized", "ilike", phone),
            ]
            if company_id:
                domain = [("company_id", "in", [company_id, False])] + domain
            partner = self.env["res.partner"].sudo().search(domain, limit=1)

        lead_ganador = data.get("lead_ganador") in (True, "true", "OUI", "oui", 1, "1")
        etat = (data.get("etat_final") or "").lower()
        sin_cp = etat in ("q3_sin_cp", "sin_cp") or data.get("codigo_postal") == "desconocido"
        amd = (data.get("amd_result") or "").lower()
        duration = int(data.get("duration_seconds") or 0)
        cost = data.get("cost_euros")
        if cost is None:
            from odoo.addons.doorway_credits.services.sofia_es_billing import compute_sofia_es_cost

            cost = compute_sofia_es_cost(duration, amd)["cost_euros"]

        timestamp = data.get("timestamp") or ""
        transcript = (data.get("transcript") or "")[:500]
        note = (
            "Sofia ES %s | Durée: %ss | Coût: %s€ | AMD: %s | État: %s\n%s"
            % (timestamp, duration, cost, amd, etat, transcript)
        )

        result = {"partner_id": partner.id if partner else False, "lead_id": False}

        if partner:
            tag_name = "Lead Qualifié ES" if lead_ganador else "Appelé Sofia ES"
            tag = self._get_or_create_tag(tag_name)
            vals = {"comment": note}
            if tag not in partner.category_id:
                vals["category_id"] = [(4, tag.id)]
            partner.write(vals)

        if lead_ganador and partner:
            Lead = self.env["crm.lead"].sudo()
            existing = Lead.search(
                [("partner_id", "=", partner.id), ("name", "ilike", "Sofia ES")],
                limit=1,
            )
            if not existing:
                tipo = data.get("tipo_vivienda") or ""
                priority = "3" if tipo == "unifamiliar" else "2"
                team = self.env["crm.team"].sudo().search(
                    [("name", "ilike", "Immobilier")], limit=1
                )
                lead_vals = {
                    "name": "Sofia ES — %s" % (partner.name or data.get("nombre") or "Prospect"),
                    "partner_id": partner.id,
                    "phone": partner.phone or data.get("telephone"),
                    "email_from": partner.email or data.get("email"),
                    "description": data.get("transcript") or note,
                    "priority": priority,
                    "type": "opportunity",
                }
                if company_id or partner.company_id:
                    lead_vals["company_id"] = company_id or partner.company_id.id
                if team:
                    lead_vals["team_id"] = team.id
                tag_lead = self._get_or_create_tag("Lead Sofia Espagne")
                lead = Lead.create(lead_vals)
                if tag_lead:
                    lead.tag_ids = [(4, tag_lead.id)]
                result["lead_id"] = lead.id
            else:
                result["lead_id"] = existing.id

        result["supervisor_callback"] = bool(lead_ganador or sin_cp)
        result["ok"] = True
        return result
