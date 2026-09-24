# -*- coding: utf-8 -*-
"""Connecteur GA4 Data API (structure Phase 2)."""
import logging

_logger = logging.getLogger(__name__)


class GA4Connector:
    def __init__(self, property_id, credentials_path=None):
        self.property_id = (property_id or "").strip()
        self.credentials_path = credentials_path

    def run_report(self, metrics=None, dimensions=None, start_date=None, end_date=None):
        if not self.property_id:
            return {"ok": False, "message": "GA4 Property ID manquant."}
        return {
            "ok": False,
            "message": (
                "GA4 Data API — placez le service account JSON et configurez "
                "doorway_traffic_manager.ga4_credentials_path."
            ),
        }
