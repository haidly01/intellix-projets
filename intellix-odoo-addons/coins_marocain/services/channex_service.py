# -*- coding: utf-8 -*-
"""Client Channex — file d'attente tant que la clé API n'est pas fournie."""
import logging
import re
import time

import requests

from odoo.addons.coins_marocain.services.channex_ari import (
    merge_availability_values,
    task_ids,
)

_logger = logging.getLogger(__name__)

PARAM_KEY = "coins.channex.api_key"
PARAM_URL = "coins.channex.base_url"
PARAM_ENABLED = "coins.channex.enabled"
DEFAULT_URL = "https://staging.channex.io/api/v1"


class ChannexNotConfigured(Exception):
    pass


class ChannexService:
    def __init__(self, env):
        self.env = env
        ICP = env["ir.config_parameter"].sudo()
        self.api_key = (ICP.get_param(PARAM_KEY) or "").strip()
        self.base_url = (ICP.get_param(PARAM_URL) or DEFAULT_URL).rstrip("/")
        self.enabled = ICP.get_param(PARAM_ENABLED, "False") == "True"

    @property
    def ready(self):
        return bool(self.enabled and self.api_key)

    def _headers(self):
        return {
            "user-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _assert_allowed_path(method, path):
        """Certif : jamais GET /bookings, GET /booking_revisions (liste) ni GET by-id."""
        clean = (path or "").split("?")[0].rstrip("/")
        method = (method or "GET").upper()
        if method != "GET":
            return
        if clean in ("/bookings", "/booking_revisions"):
            raise RuntimeError("Channex certif : pas de GET liste %s" % clean)
        if re.match(r"^/booking_revisions/[0-9a-fA-F-]{36}$", clean):
            raise RuntimeError("Channex certif : pas de GET by-id, utiliser /feed")

    def request(self, method, path, payload=None, params=None, timeout=60):
        """Retourne le JSON complet (task ids dans data[]). Retry 429 : pause 60 s."""
        if not self.ready:
            raise ChannexNotConfigured("Clé Channex absente — push mis en file")
        self._assert_allowed_path(method, path)
        url = "%s%s" % (self.base_url, path if path.startswith("/") else "/" + path)
        last_err = None
        for attempt in range(3):
            resp = requests.request(
                method,
                url,
                headers=self._headers(),
                json=payload,
                params=params,
                timeout=timeout,
            )
            try:
                body = resp.json()
            except ValueError:
                body = {"raw": resp.text[:500]}
            if resp.status_code == 429:
                last_err = body
                _logger.warning("channex 429 %s %s attempt=%s", method, path, attempt + 1)
                time.sleep(60)
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    "Channex %s %s → %s %s" % (method, path, resp.status_code, body)
                )
            return body
        raise RuntimeError("Channex 429 after retries %s %s %s" % (method, path, last_err))

    def ping(self):
        body = self.request("GET", "/properties")
        return body.get("data", body)

    def push_availability(self, values):
        """Un POST /availability — plages fusionnées, jamais un objet `date` isolé."""
        return self.request(
            "POST", "/availability", {"values": merge_availability_values(values)}
        )

    def push_restrictions(self, values):
        """Un POST /restrictions — tarif + restrictions déclarées (min stay, stop sell, CTA, CTD, max stay)."""
        return self.request("POST", "/restrictions", {"values": list(values or [])})

    @staticmethod
    def task_ids(body):
        return task_ids(body)

    def feed_booking_revisions(self, property_id=None):
        """Feed officiel — jamais GET /bookings ni GET /booking_revisions (liste)."""
        params = {}
        if property_id:
            params["filter[property_id]"] = property_id
        return self.request("GET", "/booking_revisions/feed", params=params or None)

    def list_booking_revisions(self):
        """Compat : pointe vers le feed, pas la liste (certif refuse received_via_list)."""
        return self.feed_booking_revisions()

    def ack_revision(self, revision_id):
        return self.request("POST", "/booking_revisions/%s/ack" % revision_id)

    def get_property(self, property_id):
        return self.request("GET", "/properties/%s" % property_id)

    def list_channels(self, property_uuid=None):
        """Liste les connexions canal Channex (Booking, Airbnb, …) pour un bien."""
        params = {}
        if property_uuid:
            params["filter[property_id]"] = property_uuid
        body = self.request("GET", "/channels", params=params or None)
        return body.get("data", body) if isinstance(body, dict) else body

    def create_room_type(self, property_uuid, title, occ_adults=2, count=1):
        """Crée un room_type Channex pour une chambre locale (1:1)."""
        occ = int(occ_adults or 2)
        payload = {
            "room_type": {
                "property_id": property_uuid,
                "title": (title or "Chambre")[:80],
                "count_of_rooms": int(count or 1),
                "occ_adults": occ,
                "occ_children": 0,
                "occ_infants": 0,
                "default_occupancy": occ,
            }
        }
        return self.request("POST", "/room_types", payload)

    def ensure_restriction_settings(self, property_id):
        """Inventaire 500 j + min stay arrival AND through (les deux sont cochés)."""
        body = self.get_property(property_id)
        node = (body or {}).get("data") if isinstance(body, dict) else {}
        attrs = (node or {}).get("attributes") or {}
        settings = dict(attrs.get("settings") or {})
        changed = False
        if settings.get("state_length") != 500:
            settings["state_length"] = 500
            changed = True
        if settings.get("min_stay_type") != "both":
            settings["min_stay_type"] = "both"
            changed = True
        if not changed:
            return body
        return self.request(
            "PUT",
            "/properties/%s" % property_id,
            {"property": {"settings": settings}},
        )
