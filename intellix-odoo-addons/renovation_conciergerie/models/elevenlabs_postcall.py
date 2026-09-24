# -*- coding: utf-8 -*-
"""Création / assignation webhooks post-call ElevenLabs → n8n."""
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class RenovationElevenLabsPostcall(models.AbstractModel):
    _name = "renovation.elevenlabs.postcall"
    _description = "Pont ElevenLabs post-call → n8n"

    @api.model
    def _client_and_base(self):
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            BASE,
            ElevenLabsClient,
        )

        return ElevenLabsClient(self.env), BASE

    @api.model
    def find_webhook_id_by_url(self, webhook_url):
        client, base_url = self._client_and_base()
        response = requests.get(
            "%s/workspace/webhooks" % base_url,
            headers=client.headers,
            timeout=30,
        )
        if response.status_code >= 400:
            return ""
        target = (webhook_url or "").rstrip("/")
        for wh in (response.json() or {}).get("webhooks") or []:
            if (wh.get("webhook_url") or "").rstrip("/") == target:
                return wh.get("webhook_id") or ""
        return ""

    @api.model
    def create_webhook(self, name, webhook_url):
        client, base_url = self._client_and_base()
        response = requests.post(
            "%s/workspace/webhooks" % base_url,
            headers=client.headers,
            json={
                "settings": {
                    "name": name,
                    "webhook_url": webhook_url,
                    "auth_type": "hmac",
                    "events": ["transcript"],
                    "transcript_format": "json",
                }
            },
            timeout=30,
        )
        if response.status_code >= 400:
            _logger.warning(
                "Création webhook EL %s: %s %s",
                name,
                response.status_code,
                response.text[:400],
            )
            return "", ""
        body = response.json() or {}
        return body.get("webhook_id") or "", body.get("webhook_secret") or ""

    @api.model
    def ensure_webhook(self, webhook_url, name, icp_id_key, icp_secret_key=None):
        icp = self.env["ir.config_parameter"].sudo()
        webhook_id = (icp.get_param(icp_id_key) or "").strip()
        if not webhook_id:
            webhook_id = self.find_webhook_id_by_url(webhook_url)
        if not webhook_id:
            webhook_id, secret = self.create_webhook(name, webhook_url)
            if secret and icp_secret_key and not icp.get_param(icp_secret_key):
                icp.set_param(icp_secret_key, secret)
        if webhook_id:
            icp.set_param(icp_id_key, webhook_id)
        return webhook_id

    @api.model
    def assign_webhook_to_agent_ids(self, webhook_id, agent_ids):
        if not webhook_id:
            return 0
        client, base_url = self._client_and_base()
        payload = {
            "platform_settings": {
                "workspace_overrides": {
                    "webhooks": {
                        "post_call_webhook_id": webhook_id,
                        "events": ["transcript"],
                        "transcript_format": "json",
                    }
                }
            }
        }
        updated = 0
        for agent_id in agent_ids:
            if not agent_id or str(agent_id).startswith("ELEVENLABS"):
                continue
            response = requests.patch(
                "%s/convai/agents/%s" % (base_url, agent_id),
                headers=client.headers,
                json=payload,
                timeout=60,
            )
            if response.status_code < 400:
                updated += 1
            else:
                _logger.warning(
                    "PATCH agent %s webhook: %s",
                    agent_id,
                    response.text[:300],
                )
        return updated

    @api.model
    def collect_agent_ids(self, icp_keys=None, profile_domain=None):
        ids = set()
        icp = self.env["ir.config_parameter"].sudo()
        for key in icp_keys or []:
            aid = (icp.get_param(key) or "").strip()
            if aid and not aid.startswith("ELEVENLABS"):
                ids.add(aid)
        if profile_domain:
            for profile in self.env["doorway.agent.profile"].sudo().search(
                profile_domain
            ):
                aid = (profile.external_agent_id or "").strip()
                if aid and not aid.startswith("ELEVENLABS"):
                    ids.add(aid)
        return ids
