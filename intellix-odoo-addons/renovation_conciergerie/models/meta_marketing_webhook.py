# -*- coding: utf-8 -*-
import logging
import secrets

from odoo import _, api, models

_logger = logging.getLogger(__name__)

MARKETING_META_ASSIGNEE_LOGIN = "zakaria@agencedoorway.com"


class RenovationMetaMarketingWebhook(models.AbstractModel):
    _name = "renovation.meta.marketing.webhook"
    _description = "Webhooks Meta Lead Ads — pipeline Marketing (sans agent IA)"

    @api.model
    def _ensure_marketing_meta_webhook_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("renovation_conciergerie.marketing_meta_webhook_token"):
            icp.set_param(
                "renovation_conciergerie.marketing_meta_webhook_token",
                secrets.token_urlsafe(32),
            )

    @api.model
    def _check_token(self, data):
        icp = self.env["ir.config_parameter"].sudo()
        expected = icp.get_param(
            "renovation_conciergerie.marketing_meta_webhook_token"
        )
        if not expected:
            return True
        provided = (
            data.get("token")
            or data.get("webhook_token")
        )
        return provided == expected

    @api.model
    def _resolve_assignee(self, data):
        login = (
            (data.get("assign_user_login") or "").strip()
            or MARKETING_META_ASSIGNEE_LOGIN
        )
        user = self.env["res.users"].sudo().search(
            [("login", "=", login), ("active", "=", True)],
            limit=1,
        )
        if user:
            return user
        route = self.env["renovation.meta.leads.routing"].resolve_route(data)
        login = (route.get("assign_user_login") or "").strip()
        if login:
            user = self.env["res.users"].sudo().search(
                [("login", "=", login), ("active", "=", True)],
                limit=1,
            )
            if user:
                return user
        team = self.env.ref(
            "renovation_conciergerie.crm_team_marketing",
            raise_if_not_found=False,
        )
        return team._get_default_assignee() if team else self.env["res.users"]

    @api.model
    def _marketing_company_id(self, assignee):
        Team = self.env["crm.team"]
        digital_id = Team._doorway_digital_doorway_company_id()
        if digital_id:
            return digital_id
        if assignee and assignee.company_id:
            return assignee.company_id.id
        team = self.env.ref(
            "renovation_conciergerie.crm_team_marketing",
            raise_if_not_found=False,
        )
        if team and team.company_id:
            return team.company_id.id
        return False

    @api.model
    def create_lead_from_meta_payload(self, data):
        """Lead Meta Agence Doorway → pipeline Marketing, étape Nouveau, Zakaria."""
        data = data or {}
        team = self.env.ref(
            "renovation_conciergerie.crm_team_marketing",
            raise_if_not_found=False,
        )
        if not team:
            return {
                "status": "error",
                "message": _("Équipe Marketing introuvable."),
            }, 500

        first = (data.get("first_name") or data.get("prenom") or "").strip()
        last = (data.get("last_name") or data.get("nom") or "").strip()
        full = (data.get("full_name") or "").strip()
        if full and not first:
            parts = full.split()
            first = parts[0] if parts else ""
            last = " ".join(parts[1:]) if len(parts) > 1 else last
        contact_name = " ".join(p for p in (first, last) if p).strip()
        email = (data.get("email") or data.get("email_from") or "").strip()
        phone = (
            data.get("phone")
            or data.get("phone_number")
            or data.get("mobile")
            or data.get("tel")
            or ""
        ).strip()
        partner_name = (
            data.get("partner_name")
            or data.get("company")
            or data.get("company_name")
            or ""
        ).strip()
        page_id = (
            data.get("page_id")
            or data.get("facebook_page_id")
            or ""
        ).strip()
        form_id = self.env["renovation.meta.leads.routing"]._normalize_meta_form_id(
            data.get("form_id")
            or data.get("leadgen_form_id")
            or ""
        )
        meta_lead_id = (
            data.get("meta_lead_id")
            or data.get("leadgen_id")
            or data.get("id")
            or ""
        ).strip()
        route = self.env["renovation.meta.leads.routing"].resolve_route(data)
        page_name = (route.get("page_name") or data.get("page_name") or "").strip()

        if not email and not phone:
            return {
                "status": "error",
                "message": _("Au moins un email ou un téléphone est requis."),
            }, 400

        if meta_lead_id:
            existing = self.env["crm.lead"].sudo().search(
                [
                    ("team_id", "=", team.id),
                    ("description", "ilike", f"leadgen_id: {meta_lead_id}"),
                ],
                limit=1,
            )
            if existing:
                return {
                    "status": "success",
                    "duplicate": True,
                    "lead_id": existing.id,
                    "stage_name": existing.stage_id.name,
                }, 200

        prefix = "Meta Lead Ads — Agence Doorway"
        if contact_name:
            lead_name = f"{prefix} — {contact_name}"
        elif email:
            lead_name = f"{prefix} — {email}"
        else:
            lead_name = f"{prefix} — {phone}"

        desc_lines = [
            "Source: Meta Lead Ads (page Agence Doorway).",
            "Digital Doorway — assigné à Zakaria (pas d'agent IA).",
        ]
        if page_name:
            desc_lines.append(f"Page Meta: {page_name}")
        if page_id:
            desc_lines.append(f"page_id: {page_id}")
        if form_id:
            desc_lines.append(f"form_id: {form_id}")
        if meta_lead_id:
            desc_lines.append(f"leadgen_id: {meta_lead_id}")

        assignee = self._resolve_assignee(data)
        vals = {
            "name": lead_name,
            "type": "opportunity",
            "team_id": team.id,
            "lead_provenance": "nouveau",
            "contact_name": contact_name or False,
            "partner_name": partner_name or False,
            "email_from": email or False,
            "phone": phone or False,
            "description": "\n".join(desc_lines),
            "city": (data.get("city") or "").strip() or False,
            "street": (
                data.get("street")
                or data.get("full_address")
                or data.get("address")
                or ""
            ).strip()
            or False,
            "zip": (data.get("zip") or data.get("postal_code") or "").strip() or False,
        }
        if assignee:
            vals["user_id"] = assignee.id
        company_id = self._marketing_company_id(assignee)
        if company_id:
            vals["company_id"] = company_id

        vals.update(
            self.env["renovation.website.lead.webhook"]._marketing_vals_from_payload(
                data
            )
        )

        lead = self.env["crm.lead"].sudo().create(vals)
        # user_id Zakaria peut recalculer team_id → Coins Marocain. On force Marketing.
        if lead.team_id.id != team.id:
            mkt_new = self.env["crm.stage"].sudo().search(
                [("name", "=", "Nouveau"), ("team_ids", "in", [team.id])],
                limit=1,
            )
            lead.sudo().write(
                {
                    "team_id": team.id,
                    "stage_id": mkt_new.id if mkt_new else lead.stage_id.id,
                }
            )
        stage = lead.stage_id
        return {
            "status": "success",
            "lead_id": lead.id,
            "team_id": team.id,
            "team_name": team.name,
            "stage_id": stage.id if stage else False,
            "stage_name": stage.name if stage else False,
            "lead_provenance": lead.lead_provenance,
            "user_id": lead.user_id.id if lead.user_id else False,
            "assignee": lead.user_id.name if lead.user_id else "",
        }, 200
