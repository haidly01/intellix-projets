# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DoorwayTrafficHeygenJob(models.Model):
    _name = "doorway.traffic.heygen.job"
    _description = "Job HeyGen — créatif Traffic Manager"
    _order = "create_date desc"

    creative_id = fields.Many2one(
        "doorway.creative", required=True, ondelete="cascade"
    )
    heygen_video_id = fields.Char(required=True, index=True)
    state = fields.Selection(
        [
            ("pending", "En attente"),
            ("processing", "En cours"),
            ("done", "Terminé"),
            ("failed", "Échec"),
        ],
        default="pending",
    )
    error_message = fields.Text()

    def _cron_poll_traffic_heygen_videos(self):
        jobs = self.search([("state", "in", ("pending", "processing"))])
        HeyGen = self.env["doorway.social.heygen.service"]
        Media = self.env["doorway.traffic.media.service"]
        for job in jobs:
            try:
                status = HeyGen.poll_video(job.heygen_video_id)
                if status.get("status") == "completed":
                    creative = job.creative_id
                    creative.write({
                        "video_url": status.get("video_url"),
                        "video_thumbnail": status.get("thumbnail_url"),
                        "image_url": status.get("video_url"),
                        "media_status": "video_ready",
                    })
                    if status.get("thumbnail_url"):
                        Media._download_image_url(
                            creative, status.get("thumbnail_url")
                        )
                    Media.ensure_creative_preview(creative)
                    job.state = "done"
                elif status.get("status") == "failed":
                    job.state = "failed"
                    job.error_message = status.get("error") or "HeyGen failed"
                else:
                    job.state = "processing"
            except Exception as exc:  # noqa: BLE001
                _logger.warning("HeyGen traffic poll %s: %s", job.heygen_video_id, exc)
