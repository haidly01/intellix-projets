# -*- coding: utf-8 -*-
"""WhatsApp inbound — stub reconstruit (logique complète à restaurer)."""
import json
import logging
from odoo import http
from odoo.http import request
_logger = logging.getLogger(__name__)

class CoinsWhatsappController(http.Controller):
    @http.route("/coins/api/whatsapp/inbound", type="http", auth="public", methods=["POST", "OPTIONS"], csrf=False)
    def whatsapp_inbound(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("{}", headers=[("Content-Type", "application/json")])
        _logger.warning("coins whatsapp inbound stub — full handler not restored yet")
        return request.make_response(json.dumps({"ok": True, "stub": True}), headers=[("Content-Type", "application/json")])
