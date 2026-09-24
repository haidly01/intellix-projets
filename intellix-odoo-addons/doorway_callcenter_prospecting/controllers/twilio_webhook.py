# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CallcenterTwilioWebhook(http.Controller):
    @http.route(
        "/api/callcenter/twilio/whatsapp-incoming",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_incoming(self, **post):
        phone = post.get("From") or post.get("from") or ""
        body = post.get("Body") or post.get("body") or ""
        profile = post.get("ProfileName") or post.get("profile_name") or ""
        _logger.info("Twilio incoming CC: %s → %s", phone, body[:80])
        result = (
            request.env["doorway.callcenter.prospect"]
            .sudo()
            .process_incoming_reply(phone, body, profile_name=profile)
        )
        if result.get("qualify"):
            _logger.info("Prospect qualifié démo: %s", phone)
        return request.make_response(
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            headers=[("Content-Type", "text/xml")],
        )
