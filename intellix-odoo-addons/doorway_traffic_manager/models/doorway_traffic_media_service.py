# -*- coding: utf-8 -*-
import base64
import logging
from urllib.parse import quote

import requests

from odoo import _, models

_logger = logging.getLogger(__name__)


class DoorwayTrafficMediaService(models.AbstractModel):
    _name = "doorway.traffic.media.service"
    _description = "Service médias créatifs Traffic Manager"

    def _is_video_format(self, creative):
        return (creative.format or "") in ("video", "reel", "story")

    def ensure_creative_preview(self, creative):
        """Garantit un aperçu visible (image ou miniature vidéo)."""
        creative.ensure_one()
        if creative.preview_image:
            return True
        if creative.image_url:
            if self._download_image_url(creative, creative.image_url):
                return True
        if creative.video_thumbnail:
            if self._download_image_url(creative, creative.video_thumbnail):
                creative.media_status = "video_ready"
                return True
        if self._is_video_format(creative):
            self._set_video_placeholder(creative)
        else:
            self._set_image_placeholder(creative)
        return bool(creative.preview_image)

    def _download_image_url(self, creative, url):
        if not url or not url.startswith("http"):
            return False
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200 and resp.content:
                creative.write({
                    "preview_image": base64.b64encode(resp.content),
                    "media_status": "image_ready",
                })
                return True
        except requests.RequestException as exc:
            _logger.warning("Download preview %s: %s", url[:80], exc)
        return False

    def _set_image_placeholder(self, creative):
        foundation = creative.campaign_id.foundation_id
        brand = (foundation.brand_name or "Ad")[:30]
        headline = (creative.headline or brand)[:20]
        urls = [
            "https://placehold.co/1080x1080/png/2563eb/ffffff?text=%s"
            % quote(headline),
            "https://ui-avatars.com/api/?name=%s&size=512&background=2563eb&color=fff&bold=true"
            % quote(brand),
        ]
        for url in urls:
            if self._download_image_url(creative, url):
                return
        creative.write({"media_status": "image_ready"})

    def _set_video_placeholder(self, creative):
        foundation = creative.campaign_id.foundation_id
        headline = (creative.headline or foundation.brand_name or "Video")[:24]
        urls = [
            "https://placehold.co/1080x1920/1e293b/f8fafc/png?text=%s"
            % quote(headline + " · Vidéo"),
            "https://ui-avatars.com/api/?name=%s&size=512&background=1e293b&color=f8fafc&bold=true"
            % quote(headline),
        ]
        for url in urls:
            if self._download_image_url(creative, url):
                break
        if not creative.video_script and creative.body:
            creative.video_script = creative.body
        creative.write({"media_status": "video_pending"})

    def preview_url_for_wizard(self, foundation, creative_data):
        """URL d'aperçu temporaire (wizard, avant création en base)."""
        headline = (creative_data.get("headline") or foundation.brand_name or "Ad")[:28]
        fmt = creative_data.get("format") or "image"
        if fmt in ("video", "reel", "story"):
            return (
                "https://placehold.co/1080x1920/1e293b/f8fafc/png?text=%s"
                % quote(headline + " Video")
            )
        return (
            "https://placehold.co/1080x1080/png/2563eb/ffffff?text=%s"
            % quote(headline)
        )
