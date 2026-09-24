# -*- coding: utf-8 -*-
import logging

import requests

_logger = logging.getLogger(__name__)


class N8nWhatsAppService:
    """URLs n8n WhatsApp (DEV)."""

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def _url(self, key, default):
        return (self._icp.get_param(key) or default).rstrip("/")

    def send_url(self):
        return self._url(
            "doorway_messaging.n8n_wa_send_url",
            "http://127.0.0.1:5678/webhook/wa-send",
        )

    def bulk_url(self):
        return self._url(
            "doorway_messaging.n8n_wa_bulk_url",
            "http://127.0.0.1:5678/webhook/wa-bulk",
        )

    def inbound_url(self):
        return self._url(
            "doorway_messaging.n8n_wa_inbound_url",
            "http://127.0.0.1:5678/webhook/wa-inbound",
        )

    def post_json(self, icp_key, default_url, payload, timeout=30):
        url = self._url(icp_key, default_url)
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            data = resp.json() if resp.content else {}
            return resp.status_code, data
        except Exception as exc:
            _logger.warning("n8n POST %s: %s", url, exc)
            return 0, {"success": False, "error": str(exc)}
