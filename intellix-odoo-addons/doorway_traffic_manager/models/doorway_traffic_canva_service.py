# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwayTrafficCanvaService(models.AbstractModel):
    _name = "doorway.traffic.canva.service"
    _description = "Service Canva — créatifs publicitaires Traffic Manager"

    def _canva_mcp_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_social_ia.canva_mcp_url")
            or ""
        ).strip()

    def _edit_url_template(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_traffic_manager.canva_edit_url_template")
            or "https://www.canva.com/design/{design_id}/edit"
        )

    def _build_edit_url(self, design_id):
        if not design_id:
            return ""
        template = self._edit_url_template()
        if "{design_id}" in template:
            return template.format(design_id=design_id)
        return template.rstrip("/") + "/" + design_id

    def build_brand_canva_brief(self, creative):
        creative.ensure_one()
        campaign = creative.campaign_id
        foundation = campaign.foundation_id
        parts = [
            f"Marque : {foundation.brand_name}",
            f"Offre : {foundation.main_value_prop or ''}",
            f"Angle : {creative.brand_angle or ''}",
            f"Format Meta : {creative.format or 'image'}",
            f"Titre : {creative.headline or ''}",
            f"Message : {creative.body or ''}",
            f"CTA : {creative.cta or ''}",
        ]
        if foundation.brand_voice_guide:
            parts.append(f"Ton : {foundation.brand_voice_guide[:200]}")
        if foundation.brand_vocabulary:
            parts.append(f"Vocabulaire : {foundation.brand_vocabulary[:150]}")
        if foundation.what_to_avoid:
            parts.append(f"À éviter : {foundation.what_to_avoid[:150]}")
        return "\n".join(p for p in parts if p.strip())

    def suggest_canva_brief(self, creative):
        creative.ensure_one()
        if creative.canva_brief:
            return creative.canva_brief
        foundation = creative.campaign_id.foundation_id
        payload = {
            "marque": foundation.brand_name,
            "offre": foundation.main_value_prop,
            "headline": creative.headline,
            "body": creative.body,
            "angle": creative.brand_angle,
            "format": creative.format,
            "guide_voix": foundation.brand_voice_guide,
        }
        brief = self.env["doorway.traffic.claude.service"].suggest_canva_brief(
            payload
        )
        return brief or self.build_brand_canva_brief(creative)

    def generate_creative_design(self, creative):
        """Crée ou met à jour un design Canva ancré sur la marque."""
        creative.ensure_one()
        campaign = creative.campaign_id
        foundation = campaign.foundation_id
        canva_brief = self.suggest_canva_brief(creative)
        visual = creative.visual_description or canva_brief

        mcp_url = self._canva_mcp_url()
        design_id = creative.canva_design_id or ""
        edit_url = ""
        export_url = ""

        if mcp_url:
            try:
                resp = requests.post(
                    mcp_url,
                    json={
                        "action": "create_design",
                        "description": visual,
                        "canva_brief": canva_brief,
                        "brand_name": foundation.brand_name,
                        "headline": creative.headline,
                        "body": creative.body,
                        "cta": creative.cta,
                        "format": creative.format,
                        "platform": "meta_ads",
                        "campaign": campaign.name,
                    },
                    timeout=90,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    design_id = data.get("design_id") or design_id
                    edit_url = data.get("edit_url") or ""
                    export_url = data.get("export_url") or ""
            except requests.RequestException as exc:
                _logger.warning("Canva MCP Traffic: %s", exc)

        if not edit_url and design_id:
            edit_url = self._build_edit_url(design_id)

        status = "ready" if design_id or export_url else "placeholder"
        message = ""
        if not design_id and not mcp_url:
            message = _(
                "Canva MCP non configuré — aperçu placeholder généré. "
                "Renseignez l'URL MCP dans Traffic Manager → Paramètres, "
                "ou saisissez un ID design Canva sur le créatif."
            )
        elif mcp_url and not design_id and not export_url:
            message = _(
                "Appel Canva MCP sans réponse exploitable — vérifiez l'URL MCP "
                "et que le service est joignable."
            )
            status = "placeholder"

        creative.write({
            "canva_brief": canva_brief,
            "visual_description": visual,
            "canva_design_id": design_id or creative.canva_design_id,
            "canva_design_url": edit_url or creative.canva_design_url,
            "image_url": export_url or creative.image_url,
        })
        Media = self.env["doorway.traffic.media.service"]
        if export_url:
            Media._download_image_url(creative, export_url)
        else:
            Media.ensure_creative_preview(creative)

        if message:
            campaign.message_post(body=message)
        else:
            campaign.message_post(
                body=_("Design Canva généré pour le créatif « %s ».") % (
                    creative.headline or creative.id
                )
            )
        return {
            "design_id": design_id,
            "edit_url": edit_url,
            "export_url": export_url,
            "status": status,
            "message": message,
        }

    def generate_for_wizard(self, foundation, creative_data):
        """Génération Canva depuis le wizard (sans enregistrement créatif)."""
        foundation.ensure_one()
        canva_brief = creative_data.get("canva_brief") or ""
        if not canva_brief:
            canva_brief = "\n".join([
                f"Marque : {foundation.brand_name}",
                f"Offre : {foundation.main_value_prop or ''}",
                f"Titre : {creative_data.get('headline') or ''}",
                f"Message : {creative_data.get('body') or ''}",
                f"CTA : {creative_data.get('cta') or ''}",
                f"Format : {creative_data.get('format') or 'image'}",
            ])
        visual = creative_data.get("visual_description") or canva_brief
        mcp_url = self._canva_mcp_url()
        design_id = ""
        edit_url = ""
        export_url = ""

        if mcp_url:
            try:
                resp = requests.post(
                    mcp_url,
                    json={
                        "action": "create_design",
                        "description": visual,
                        "canva_brief": canva_brief,
                        "brand_name": foundation.brand_name,
                        "headline": creative_data.get("headline"),
                        "body": creative_data.get("body"),
                        "cta": creative_data.get("cta"),
                        "format": creative_data.get("format"),
                        "platform": "meta_ads",
                        "campaign": creative_data.get("headline"),
                    },
                    timeout=90,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    design_id = data.get("design_id") or ""
                    edit_url = data.get("edit_url") or ""
                    export_url = data.get("export_url") or ""
            except requests.RequestException as exc:
                _logger.warning("Canva wizard: %s", exc)

        if not edit_url and design_id:
            edit_url = self._build_edit_url(design_id)

        Media = self.env["doorway.traffic.media.service"]
        preview_url = export_url or Media.preview_url_for_wizard(
            foundation, creative_data
        )
        message = ""
        if not mcp_url:
            message = _(
                "Canva MCP non configuré — placeholder affiché. "
                "Configurez l'URL dans Traffic Manager → Paramètres."
            )
        elif not design_id and not export_url:
            message = _(
                "Canva MCP joignable mais sans design exporté — vérifiez le service."
            )
        return {
            "canva_brief": canva_brief,
            "canva_design_id": design_id,
            "canva_design_url": edit_url,
            "image_url": export_url,
            "preview_url": preview_url,
            "media_status": "image_ready" if export_url else "placeholder",
            "message": message,
        }
