# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .doorway_campaign import FOUNDATION_ZONE_MAP, ZONE_BENCHMARKS


class DoorwayTrafficCampaignWizard(models.TransientModel):
    _name = "doorway.traffic.campaign.wizard"
    _description = "Assistant création campagne Traffic Manager"

    @api.model
    def wizard_get_init(self):
        """Données initiales : canaux, marques validées, zones."""
        channels = self.env["doorway.traffic.channel"].search(
            [], order="sequence, name"
        )
        channel_rows = [
            {"code": c.code, "name": c.name, "id": c.id}
            for c in channels
        ]
        for extra in (
            {"code": "backlink", "name": "Backlink", "id": False},
            {"code": "annuaire", "name": "Annuaire", "id": False},
        ):
            if not any(r["code"] == extra["code"] for r in channel_rows):
                channel_rows.append(extra)

        foundations = self.env["doorway.brand.foundation"].search(
            [("state", "=", "validated")],
            order="brand_name",
        )
        return {
            "channels": channel_rows,
            "foundations": [
                {
                    "id": f.id,
                    "name": f.brand_name,
                    "zone": FOUNDATION_ZONE_MAP.get(f.geographic_zone, "europe"),
                }
                for f in foundations
            ],
            "zones": [
                {
                    "code": code,
                    "label": label,
                    "target_cpa": ZONE_BENCHMARKS[code][0],
                    "currency": ZONE_BENCHMARKS[code][1],
                }
                for code, label in [
                    ("canada", "🇨🇦 Canada"),
                    ("europe", "🇪🇺 Europe"),
                    ("maroc", "🇲🇦 Maroc"),
                ]
            ],
        }

    @api.model
    def wizard_chat(self, foundation_id, channel_code, zone, message,
                    history=None, budget_daily=None):
        """Étape 3 — échange conversationnel multi-tours avec Claude."""
        foundation = self.env["doorway.brand.foundation"].browse(foundation_id)
        if not foundation.exists() or foundation.state != "validated":
            raise UserError(_("Sélectionnez une marque validée."))
        channel = self._resolve_channel(channel_code)
        val, cur = ZONE_BENCHMARKS.get(zone or "europe", (15.0, "EUR"))
        Claude = self.env["doorway.traffic.claude.service"]
        result = Claude.wizard_campaign_brief({
            "marque": foundation.brand_name,
            "canal": channel.name if channel else channel_code,
            "zone": zone,
            "cpa_objectif": val,
            "devise": cur,
            "message": message,
            "historique": history or [],
            "budget_journalier": budget_daily,
        })
        return result

    @api.model
    def wizard_chat_start(self, foundation_id, channel_code, zone, budget_daily):
        """Premier message IA à l'entrée de l'étape Brief."""
        return self.wizard_chat(
            foundation_id, channel_code, zone, "[INIT]", [], budget_daily
        )

    @api.model
    def wizard_generate(self, foundation_id, channel_code, zone, brief_summary,
                        budget_daily, campaign_name):
        """Étape 4-5 — génère audiences et créatifs proposés."""
        foundation = self.env["doorway.brand.foundation"].browse(foundation_id)
        if not foundation.exists():
            raise UserError(_("Marque introuvable."))
        channel = self._resolve_channel(channel_code)
        Campaign = self.env["doorway.traffic.campaign"]
        temp = Campaign.new({
            "name": campaign_name or _("Nouvelle campagne"),
            "foundation_id": foundation.id,
            "channel_id": channel.id if channel else False,
            "zone": zone or "europe",
            "objective": "leads",
            "budget_daily": budget_daily or 50.0,
            "budget_total": (budget_daily or 50.0) * 30,
            "optimization_brief": brief_summary,
        })
        Claude = self.env["doorway.traffic.claude.service"]
        payload_extra = {
            "brief_utilisateur": brief_summary,
            "zone": zone,
            "cpa_objectif": temp.target_cpa,
            "devise": temp.target_cpa_currency,
        }
        data = Claude.generate_campaign_wizard(temp, foundation, payload_extra)
        audiences = data.get("audiences", [])
        creatives = data.get("creatives", [])
        Media = self.env["doorway.traffic.media.service"]
        creative_rows = []
        for cr in creatives:
            row = {
                "format": cr.get("format") or "image",
                "headline": cr.get("headline") or "",
                "body": cr.get("body") or "",
                "cta": cr.get("cta") or "En savoir plus",
                "angle": cr.get("angle") or "",
                "rationale": cr.get("rationale") or "",
                "canva_brief": cr.get("canva_brief") or "",
                "video_script": cr.get("body") or "",
                "accepted": True,
                "preview_url": Media.preview_url_for_wizard(foundation, cr),
                "media_status": "none",
                "generating_media": False,
            }
            creative_rows.append(row)
        return {
            "strategy_notes": data.get("strategy_notes") or "",
            "audiences": [
                {
                    "name": a.get("name") or "Audience",
                    "description": a.get("description") or "",
                    "audience_type": a.get("audience_type") or "cold",
                    "platform": a.get("platform") or channel_code,
                    "targeting_rationale": a.get("targeting_rationale")
                    or a.get("description")
                    or "",
                    "estimated_size": a.get("estimated_size") or 0,
                    "accepted": True,
                }
                for a in audiences
            ],
            "creatives": creative_rows,
            "budget_daily": budget_daily,
            "campaign_name": campaign_name,
        }

    @api.model
    def wizard_create(self, foundation_id, channel_code, zone, brief_summary,
                      budget_daily, campaign_name, audiences, creatives):
        """Crée la campagne + enfants — statut ai_proposed (validation humaine)."""
        foundation = self.env["doorway.brand.foundation"].browse(foundation_id)
        if not foundation.exists() or foundation.state != "validated":
            raise UserError(_("La marque doit être validée avant création."))
        channel = self._resolve_channel(channel_code)
        accepted_aud = [a for a in (audiences or []) if a.get("accepted", True)]
        accepted_cr = [c for c in (creatives or []) if c.get("accepted", True)]
        if not accepted_aud:
            raise UserError(_("Sélectionnez au moins une audience."))
        if not accepted_cr:
            raise UserError(_("Sélectionnez au moins un créatif."))

        campaign = self.env["doorway.traffic.campaign"].create({
            "name": campaign_name or _("Campagne %s") % foundation.brand_name,
            "foundation_id": foundation.id,
            "channel_id": channel.id if channel else False,
            "zone": zone or "europe",
            "objective": "leads",
            "budget_daily": budget_daily or 50.0,
            "budget_total": (budget_daily or 50.0) * 30,
            "optimization_brief": brief_summary,
            "ai_status": "ai_proposed",
            "ai_recommendation": brief_summary,
        })

        Audience = self.env["doorway.audience"]
        for aud in accepted_aud:
            targeting = aud.get("targeting") or {}
            Audience.create({
                "campaign_id": campaign.id,
                "name": aud.get("name") or "Audience",
                "description": aud.get("description"),
                "audience_type": aud.get("audience_type") or "cold",
                "platform": aud.get("platform") or channel_code,
                "targeting": json.dumps(targeting, ensure_ascii=False)
                if isinstance(targeting, dict)
                else targeting,
                "targeting_rationale": aud.get("targeting_rationale"),
                "estimated_size": aud.get("estimated_size") or 0,
                "source": "ai_generated",
                "ai_status": "proposed",
            })

        Creative = self.env["doorway.creative"]
        Media = self.env["doorway.traffic.media.service"]
        HeygenJob = self.env["doorway.traffic.heygen.job"]
        for cr in accepted_cr:
            creative = Creative.create({
                "campaign_id": campaign.id,
                "format": cr.get("format") or "image",
                "headline": cr.get("headline"),
                "body": cr.get("body"),
                "cta": cr.get("cta"),
                "brand_angle": cr.get("angle"),
                "creative_rationale": cr.get("rationale"),
                "canva_brief": cr.get("canva_brief"),
                "canva_design_id": cr.get("canva_design_id"),
                "canva_design_url": cr.get("canva_design_url"),
                "image_url": cr.get("image_url"),
                "video_script": cr.get("video_script"),
                "video_url": cr.get("video_url"),
                "heygen_video_id": cr.get("heygen_video_id"),
                "media_status": cr.get("media_status") or "none",
                "ai_status": "proposed",
            })
            if cr.get("image_url"):
                Media._download_image_url(creative, cr["image_url"])
            else:
                Media.ensure_creative_preview(creative)
            if cr.get("heygen_video_id"):
                HeygenJob.create({
                    "creative_id": creative.id,
                    "heygen_video_id": cr["heygen_video_id"],
                })

        self.env["doorway.traffic.log"].sudo().create({
            "campaign_id": campaign.id,
            "action": _("Campagne créée via assistant IA"),
            "source": "human",
            "details": brief_summary,
        })
        campaign.message_post(
            body=_(
                "Campagne créée par l'assistant IA — "
                "%(aud)s audience(s), %(cr)s créatif(s) en attente de validation."
            ) % {"aud": len(accepted_aud), "cr": len(accepted_cr)}
        )
        return {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
        }

    @api.model
    def wizard_generate_canva(self, foundation_id, creative):
        """Étape 5 — génère un visuel Canva pour un créatif du wizard."""
        foundation = self.env["doorway.brand.foundation"].browse(foundation_id)
        if not foundation.exists():
            raise UserError(_("Marque introuvable."))
        Canva = self.env["doorway.traffic.canva.service"]
        return Canva.generate_for_wizard(foundation, creative or {})

    @api.model
    def wizard_generate_heygen(self, foundation_id, creative):
        """Étape 5 — lance HeyGen pour un créatif vidéo du wizard."""
        foundation = self.env["doorway.brand.foundation"].browse(foundation_id)
        if not foundation.exists():
            raise UserError(_("Marque introuvable."))
        Heygen = self.env["doorway.traffic.heygen.service"]
        return Heygen.generate_for_wizard(foundation, creative or {})

    @api.model
    def wizard_generate_all_media(self, foundation_id, creatives):
        """Génère Canva ou HeyGen pour tous les créatifs acceptés."""
        foundation = self.env["doorway.brand.foundation"].browse(foundation_id)
        results = []
        for cr in creatives or []:
            if not cr.get("accepted", True):
                continue
            fmt = cr.get("format") or "image"
            try:
                if fmt in ("video", "reel", "story"):
                    res = self.wizard_generate_heygen(foundation_id, cr)
                else:
                    res = self.wizard_generate_canva(foundation_id, cr)
                cr.update(res)
                results.append({"headline": cr.get("headline"), "ok": True})
            except UserError as exc:
                results.append({
                    "headline": cr.get("headline"),
                    "ok": False,
                    "error": str(exc),
                })
        return {"creatives": creatives, "results": results}

    @api.model
    def get_integration_settings(self):
        icp = self.env["ir.config_parameter"].sudo()
        canva = (icp.get_param("doorway_social_ia.canva_mcp_url") or "").strip()
        heygen = (icp.get_param("doorway_social_ia.heygen_api_key") or "").strip()
        return {
            "canva_mcp_url": canva,
            "heygen_api_key": heygen,
            "canva_configured": bool(canva),
            "heygen_configured": bool(heygen),
        }

    @api.model
    def save_integration_settings(self, values=None):
        values = values or {}
        icp = self.env["ir.config_parameter"].sudo()
        if "canva_mcp_url" in values:
            icp.set_param(
                "doorway_social_ia.canva_mcp_url",
                (values.get("canva_mcp_url") or "").strip(),
            )
        if values.get("heygen_api_key"):
            icp.set_param(
                "doorway_social_ia.heygen_api_key",
                values["heygen_api_key"].strip(),
            )
        return self.get_integration_settings()

    def _resolve_channel(self, channel_code):
        if not channel_code or channel_code in ("backlink", "annuaire"):
            return self.env["doorway.traffic.channel"]
        return self.env["doorway.traffic.channel"].search(
            [("code", "=", channel_code)], limit=1
        )
