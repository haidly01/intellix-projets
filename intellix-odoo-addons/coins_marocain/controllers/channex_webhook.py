# -*- coding: utf-8 -*-
"""Webhook Channex — ACK HTTP immédiat (notes.success == true), sans appel API."""
import json
import logging
import threading
import time

from odoo import api, http
from odoo.http import request
from werkzeug.wrappers import Response

_logger = logging.getLogger(__name__)

_SUCCESS = json.dumps({"success": True, "notes": {"success": True}})


def _ack():
    resp = Response(_SUCCESS, status=200, mimetype="application/json")
    resp.headers["Cache-Control"] = "no-store"
    return resp


class CoinsChannexWebhookController(http.Controller):
    @http.route(
        [
            "/coins_marocain/channex/webhook",
            "/api/channex/webhook",
            "/api/coins_marocain/channex/webhook",
            "/api/coins-marocain/channex/webhook",
            "/channex/webhook",
            "/intellix/channex/webhook",
        ],
        type="http",
        auth="public",
        methods=["GET", "POST", "OPTIONS"],
        csrf=False,
        website=False,
        sitemap=False,
    )
    def channex_webhook(self, **kw):
        if request.httprequest.method in ("GET", "OPTIONS"):
            return _ack()
        raw = request.httprequest.get_data(as_text=True) or "{}"
        dbname = request.env.cr.dbname
        uid = request.env.uid or 1

        def _after_ack():
            time.sleep(0.25)
            try:
                registry = api.Registry(dbname)
                with registry.cursor() as cr:
                    env = api.Environment(cr, uid, {})
                    env["coins.channex.revision"].sudo().queue_webhook_only(raw)
                    env["coins.channex.revision"].sudo().process_after_webhook()
                    cr.commit()
            except Exception:  # noqa: BLE001
                _logger.exception("channex webhook after-ack")

        threading.Thread(target=_after_ack, name="channex-webhook-after", daemon=True).start()
        return _ack()
