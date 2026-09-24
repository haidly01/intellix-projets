# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class DoorwaySocialHeygenService(models.AbstractModel):
    _name = "doorway.social.heygen.service"
    _description = "Service HeyGen — vidéos avatar IA"

    def _api_key(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.heygen_api_key"
        ) or ""

    def _default_avatar(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.heygen_default_avatar_id"
        ) or ""

    def _default_voice(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.heygen_default_voice_id"
        ) or ""

    def generate_video(self, post):
        import requests

        key = self._api_key()
        if not key:
            _logger.info("HeyGen non configuré — mode brouillon pour post %s", post.id)
            return {"video_id": False, "status": "skipped"}

        avatar = post._get_avatar_id() or self._default_avatar()
        voice = post._get_voice_id() or self._default_voice()
        try:
            resp = requests.post(
                "https://api.heygen.com/v2/video/generate",
                headers={
                    "X-Api-Key": key,
                    "Content-Type": "application/json",
                },
                json={
                    "video_inputs": [{
                        "character": {"type": "avatar", "avatar_id": avatar},
                        "voice": {
                            "type": "text",
                            "input_text": post.video_script or post.hook or "",
                            "voice_id": voice,
                        },
                    }],
                    "dimension": {"width": 1080, "height": 1920}
                    if post.post_format in ("reel", "story")
                    else {"width": 1920, "height": 1080},
                },
                timeout=60,
            )
            if resp.status_code >= 400:
                _logger.warning("HeyGen HTTP %s: %s", resp.status_code, resp.text[:200])
                return {"video_id": False}
            data = resp.json().get("data") or resp.json()
            return {"video_id": data.get("video_id")}
        except Exception as exc:  # noqa: BLE001
            _logger.warning("HeyGen generate: %s", exc)
            return {"video_id": False}

    def poll_video(self, video_id):
        import requests

        key = self._api_key()
        if not key or not video_id:
            return {"status": "failed", "error": "HeyGen non configuré"}
        try:
            resp = requests.get(
                f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
                headers={"X-Api-Key": key},
                timeout=30,
            )
            data = resp.json().get("data") or {}
            status = (data.get("status") or "").lower()
            if status == "completed":
                return {
                    "status": "completed",
                    "video_url": data.get("video_url"),
                    "thumbnail_url": data.get("thumbnail_url"),
                }
            if status in ("failed", "error"):
                return {"status": "failed", "error": data.get("error")}
            return {"status": "processing"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "error": str(exc)}
