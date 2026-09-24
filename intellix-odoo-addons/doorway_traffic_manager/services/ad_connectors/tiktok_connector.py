# -*- coding: utf-8 -*-
"""Connecteur TikTok Ads API (structure Phase 2)."""
import logging

_logger = logging.getLogger(__name__)


class TikTokAdsConnector:
    def __init__(self, access_token, advertiser_id):
        self.access_token = (access_token or "").strip()
        self.advertiser_id = (advertiser_id or "").strip()

    def fetch_reports(self, campaign_id):
        if not self.access_token or not self.advertiser_id:
            return {"ok": False, "message": "TikTok Ads token / advertiser_id manquant."}
        return {"ok": False, "message": "TikTok Ads API — configuration requise."}
