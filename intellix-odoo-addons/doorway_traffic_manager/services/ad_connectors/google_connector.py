# -*- coding: utf-8 -*-
"""Connecteur Google Ads API (structure Phase 2)."""
import logging

import requests

_logger = logging.getLogger(__name__)


class GoogleAdsConnector:
    def __init__(self, customer_id, developer_token=None, refresh_token=None):
        self.customer_id = (customer_id or "").replace("-", "").strip()
        self.developer_token = developer_token
        self.refresh_token = refresh_token

    def _configured(self):
        icp = None
        return bool(self.customer_id and self.refresh_token)

    def fetch_campaign_metrics(self, campaign_id):
        if not self._configured():
            return {
                "ok": False,
                "message": (
                    "Google Ads non configuré — renseignez customer_id et "
                    "refresh_token dans Paramètres Traffic Manager."
                ),
            }
        _logger.info("Google Ads fetch stub for campaign %s", campaign_id)
        return {"ok": False, "message": "Google Ads API v17 — OAuth à finaliser."}

    def create_campaign(self, name, daily_budget_micros=50000000):
        if not self._configured():
            return {"ok": False, "message": "Google Ads non configuré."}
        return {"ok": False, "message": "Création Google Ads — Phase 2b."}
