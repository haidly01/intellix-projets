# -*- coding: utf-8 -*-
import base64
import logging
import uuid

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class CanvaMcpError(Exception):
    """Erreur structurée pour l'app Canva — jamais de message brut vers l'UI."""

    def __init__(self, error_code, http_status=400):
        super().__init__(error_code)
        self.error_code = error_code
        self.http_status = http_status


class DoorwaySocialCanvaService(models.AbstractModel):
    _name = "doorway.social.canva.service"
    _description = "Service Canva — MCP Intellix + publication"

    def _base_url(self):
        return (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")

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

    def handle_get_publish_config(self):
        pipelines = self.env["crm.team"].search([], order="name")
        return {
            "pipelines": [
                {"id": p.id, "name": p.name} for p in pipelines
            ],
            "platforms": [
                {"id": "instagram", "name": "Instagram"},
                {"id": "facebook", "name": "Facebook"},
                {"id": "linkedin", "name": "LinkedIn"},
                {"id": "pinterest", "name": "Pinterest"},
            ],
        }

    def handle_create_design(self, payload):
        """Contrat Traffic Manager / doorway.traffic.canva.service."""
        design_id = payload.get("design_id") or f"draft-{uuid.uuid4().hex[:12]}"
        edit_url = self._build_edit_url(design_id) if design_id.startswith("DA") else ""
        return {
            "design_id": design_id,
            "edit_url": edit_url,
            "export_url": payload.get("export_url") or "",
            "status": "placeholder",
            "message": _(
                "Brief enregistré. Créez le visuel dans Canva puis publiez via "
                "l'app Intellix Content Publisher."
            ),
            "canva_brief": payload.get("canva_brief") or payload.get("description") or "",
        }

    def handle_publish_content(self, payload):
        """Réception depuis l'app Canva Content Publisher."""
        caption = (payload.get("caption") or "").strip()
        if not caption:
            raise CanvaMcpError("caption_required")

        pipeline_id = int(payload.get("pipeline_id") or 0)
        pipeline = self.env["crm.team"].browse(pipeline_id)
        if not pipeline.exists():
            pipeline = self.env["crm.team"].search([], limit=1)
        if not pipeline:
            raise CanvaMcpError("pipeline_not_configured")

        platform = payload.get("platform") or "instagram"
        post_format = payload.get("post_format") or "publication"
        if payload.get("output_type_id") == "story":
            post_format = "story"
        elif payload.get("output_type_id") == "reel":
            post_format = "reel"

        post = self.env["doorway.social.post"].create(
            {
                "pipeline_id": pipeline.id,
                "platform": platform,
                "post_format": post_format,
                "caption": caption,
                "hook": caption[:120],
                "visual_description": caption,
                "canva_design_id": payload.get("design_id") or "",
                "state": "draft",
            }
        )

        media_b64 = payload.get("media_b64") or ""
        media_url = payload.get("media_url") or ""
        if media_b64:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": f"canva-{post.id}.png",
                    "datas": media_b64,
                    "res_model": "doorway.social.post",
                    "res_id": post.id,
                    "mimetype": payload.get("media_mimetype") or "image/png",
                }
            )
            post.attachment_ids = [(4, attachment.id)]
            post.image_url = f"/web/image/ir.attachment/{attachment.id}/datas"
        elif media_url:
            post.image_url = media_url

        base = self._base_url()
        external_url = f"{base}/odoo/action-doorway_social_ia.action_social_calendar/{post.id}"
        return {
            "status": "completed",
            "external_id": str(post.id),
            "external_url": external_url,
            "post_id": post.id,
        }

    def generate_design(self, post):
        """Génération Canva via MCP (rétrocompat posts sociaux)."""
        mcp_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_social_ia.canva_mcp_url")
            or ""
        ).strip()
        design_id = f"draft-{uuid.uuid4().hex[:12]}"
        if not mcp_url:
            _logger.info(
                "Canva MCP non configuré — design placeholder post %s", post.id
            )
            return {
                "design_id": design_id,
                "edit_url": "",
                "export_url": "",
            }
        try:
            import requests

            resp = requests.post(
                mcp_url,
                json={
                    "action": "create_design",
                    "description": post.visual_description or post.hook,
                    "platform": post.platform,
                    "format": post.post_format,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Canva MCP: %s", exc)
        return {
            "design_id": design_id,
            "edit_url": "",
            "export_url": "",
        }
