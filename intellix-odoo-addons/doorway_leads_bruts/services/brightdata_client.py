# -*- coding: utf-8 -*-
"""Client Bright Data Web Unlocker - optionnel."""
import json
import logging
import os

import requests

_logger = logging.getLogger(__name__)

BRIGHTDATA_URL = "https://api.brightdata.com/request"
CONF_PATH = "/etc/odoo-server.conf"
TIMEOUT = 120


def _read_conf_value(key):
    try:
        with open(CONF_PATH, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line[0] in "#;" or "=" not in line:
                    continue
                conf_key, conf_val = line.split("=", 1)
                if conf_key.strip() == key:
                    return conf_val.strip()
    except OSError:
        pass
    return ""


def _config():
    api_key = (os.environ.get("BRIGHTDATA_API_KEY") or _read_conf_value("BRIGHTDATA_API_KEY") or "").strip()
    zone = (
        os.environ.get("BRIGHTDATA_ZONE")
        or _read_conf_value("BRIGHTDATA_ZONE")
        or "web_unlocker1"
    ).strip()
    country = (
        os.environ.get("BRIGHTDATA_COUNTRY")
        or _read_conf_value("BRIGHTDATA_COUNTRY")
        or "ca"
    ).strip().lower()
    if not api_key:
        return None
    return {"api_key": api_key, "zone": zone, "country": country}


def is_available():
    return bool(_config())


def unlocker_get(url, extra_headers=None):
    cfg = _config()
    if not cfg:
        return ""
    payload = {
        "zone": cfg["zone"],
        "url": url,
        "format": "raw",
        "country": cfg["country"],
    }
    headers = {"Accept-Language": "fr-CA,fr;q=0.9"}
    if extra_headers:
        headers.update(extra_headers)
    payload["headers"] = headers
    try:
        resp = requests.post(
            BRIGHTDATA_URL,
            headers={
                "Authorization": "Bearer %s" % cfg["api_key"],
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=TIMEOUT,
        )
    except Exception as exc:
        _logger.warning("Bright Data GET failed %s: %s", url, exc)
        return ""
    err = resp.headers.get("x-brd-error")
    if err:
        _logger.warning("Bright Data error %s: %s", url, err)
        return ""
    if resp.status_code != 200:
        _logger.warning("Bright Data HTTP %s for %s", resp.status_code, url)
        return ""
    return resp.text or ""
