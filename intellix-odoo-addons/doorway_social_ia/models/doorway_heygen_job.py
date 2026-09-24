# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DoorwayHeygenJob(models.Model):
    _name = "doorway.heygen.job"
    _description = "Job polling vidéo HeyGen"
    _order = "create_date desc"

    post_id = fields.Many2one(
        "doorway.social.post", required=True, ondelete="cascade"
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

    def _cron_poll_heygen_videos(self):
        jobs = self.search([("state", "in", ("pending", "processing"))])
        HeyGen = self.env["doorway.social.heygen.service"]
        for job in jobs:
            try:
                status = HeyGen.poll_video(job.heygen_video_id)
                if status.get("status") == "completed":
                    job.post_id.write({
                        "video_url": status.get("video_url"),
                        "video_thumbnail": status.get("thumbnail_url"),
                        "state": "ready",
                    })
                    job.state = "done"
                elif status.get("status") == "failed":
                    job.state = "failed"
                    job.error_message = status.get("error") or "HeyGen failed"
                    job.post_id.state = "failed"
                else:
                    job.state = "processing"
            except Exception as exc:  # noqa: BLE001
                _logger.warning("HeyGen poll %s: %s", job.heygen_video_id, exc)
