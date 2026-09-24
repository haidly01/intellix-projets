# -*- coding: utf-8 -*-
"""Stats AMD depuis vicidial_log / API."""
import logging

_logger = logging.getLogger(__name__)


class AmdMonitor:
    def __init__(self, env):
        self.env = env
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        self._svc = VicidialService(env)

    def get_campaign_amd_stats(self, campaign_id=None):
        if not campaign_id or not self._svc.is_available():
            return {"human": 0, "machine": 0, "total": 0, "rows": []}
        try:
            amd = self._svc.get_amd_stats(campaign_id)
            by = amd.get("by_status") or {}
            human = by.get("HUMAN", 0) + by.get("A", 0)
            machine = sum(v for k, v in by.items() if k in ("AMD", "AA", "AM"))
            return {
                "human": human,
                "machine": machine,
                "total": amd.get("total", 0),
                "rows": [{"status": k, "count": v} for k, v in by.items()],
            }
        except Exception as exc:  # noqa: BLE001
            _logger.warning("get_campaign_amd_stats: %s", exc)
            return {"human": 0, "machine": 0, "total": 0, "rows": []}
