# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields, models


class DoorwaySocialAnalyticsService(models.AbstractModel):
    _name = "doorway.social.analytics.service"
    _description = "Analytics et meilleurs horaires IA"

    DEFAULT_TIMES = {
        "facebook": 10,
        "instagram": 11,
        "tiktok": 19,
        "linkedin": 8,
        "pinterest": 20,
        "youtube": 17,
    }

    def compute_best_time(self, post):
        hour = self.DEFAULT_TIMES.get(post.platform, 10)
        base = post.scheduled_date or fields.Datetime.now()
        if isinstance(base, str):
            base = fields.Datetime.from_string(base)
        return base.replace(hour=hour, minute=0, second=0) + timedelta(days=0)

    def sync_post_analytics(self, post):
        """Stub — à brancher sur APIs Meta/TikTok/etc."""
        return True

    def cron_sync_all_analytics(self):
        posts = self.env["doorway.social.post"].search([
            ("state", "=", "published"),
        ], limit=200)
        for post in posts:
            self.sync_post_analytics(post)
