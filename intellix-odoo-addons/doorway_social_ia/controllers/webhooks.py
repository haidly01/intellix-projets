# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DoorwaySocialWebhooks(http.Controller):

    @staticmethod
    def _whatsapp_message_content(msg):
        msg_type = msg.get("type") or "text"
        if msg_type == "text":
            return (msg.get("text") or {}).get("body") or ""
        if msg_type == "button":
            return (msg.get("button") or {}).get("text") or ""
        if msg_type == "interactive":
            interactive = msg.get("interactive") or {}
            button = interactive.get("button_reply") or {}
            list_reply = interactive.get("list_reply") or {}
            return button.get("title") or list_reply.get("title") or ""
        if msg_type in ("image", "video", "audio", "document", "sticker"):
            media = msg.get(msg_type) or {}
            caption = media.get("caption") or ""
            return caption or "[%s]" % msg_type
        return ""

    def _process_whatsapp_payload(self, data):
        Inbox = request.env["doorway.social.inbox"].sudo()
        for entry in data.get("entry") or []:
            for change in entry.get("changes") or []:
                val = change.get("value") or {}
                phone_id = (val.get("metadata") or {}).get("phone_number_id")
                contacts = {
                    (c.get("wa_id") or ""): (c.get("profile") or {}).get("name")
                    for c in (val.get("contacts") or [])
                }
                for msg in val.get("messages") or []:
                    from_id = msg.get("from") or ""
                    text = self._whatsapp_message_content(msg)
                    media_url = ""
                    media_type = False
                    msg_type = msg.get("type") or "text"
                    if msg_type in ("image", "video", "audio", "document", "sticker"):
                        media = msg.get(msg_type) or {}
                        media_url = media.get("id") or media.get("link") or ""
                        media_type = (
                            "image"
                            if msg_type == "image"
                            else "video"
                            if msg_type == "video"
                            else "audio"
                            if msg_type == "audio"
                            else "file"
                        )
                    Inbox._handle_inbound(
                        platform="whatsapp",
                        external_id=from_id,
                        content=text,
                        contact_name=contacts.get(from_id) or from_id,
                        contact_phone=from_id,
                        account_phone=phone_id,
                        external_msg_id=msg.get("id"),
                        media_url=media_url or None,
                    )

    @http.route(
        "/doorway/social/webhook/whatsapp",
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def webhook_whatsapp_post(self, **kwargs):
        try:
            data = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            _logger.warning("WhatsApp webhook: JSON invalide")
            return request.make_response("Bad JSON", status=400)
        try:
            self._process_whatsapp_payload(data)
        except Exception:
            _logger.exception("WhatsApp webhook: erreur traitement")
            return request.make_response('{"ok": false}', status=500)
        return request.make_response(
            json.dumps({"ok": True}),
            headers=[("Content-Type", "application/json")],
        )

    @http.route("/doorway/social/webhook/whatsapp", type="http", auth="public", csrf=False, methods=["GET"])
    def webhook_whatsapp_verify(self, **kwargs):
        token = request.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.whatsapp_webhook_verify_token"
        ) or "doorway_wa_2026"
        mode = kwargs.get("hub.mode")
        challenge = kwargs.get("hub.challenge")
        verify = kwargs.get("hub.verify_token")
        if mode == "subscribe" and verify == token:
            return challenge or ""
        return "Forbidden"

    @http.route("/doorway/social/webhook/telegram/<string:bot_token>", type="json", auth="public", csrf=False, methods=["POST"])
    def webhook_telegram(self, bot_token, **kwargs):
        data = request.get_json_data() or {}
        msg = data.get("message") or {}
        chat = msg.get("chat") or {}
        text = msg.get("text") or ""
        from_user = msg.get("from") or {}
        name = " ".join(
            p for p in (from_user.get("first_name"), from_user.get("last_name")) if p
        )
        request.env["doorway.social.inbox"].sudo()._handle_inbound(
            platform="telegram",
            external_id=str(chat.get("id") or ""),
            content=text,
            contact_name=name or str(chat.get("id")),
            external_msg_id=str(msg.get("message_id") or ""),
        )
        return {"ok": True}

    @http.route("/doorway/social/webhook/messenger", type="http", auth="public", csrf=False, methods=["POST"])
    def webhook_messenger(self, **kwargs):
        try:
            data = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            _logger.warning("Messenger webhook: JSON invalide")
            return request.make_response("Bad JSON", status=400)
        Inbox = request.env["doorway.social.inbox"].sudo()
        Account = request.env["doorway.social.account"].sudo()
        try:
            for entry in data.get("entry") or []:
                page_id = str(entry.get("id") or "")
                account = Account.search(
                    [
                        ("platform", "=", "facebook"),
                        ("external_account_id", "=", page_id),
                        ("connection_state", "=", "connected"),
                    ],
                    limit=1,
                )
                for msg_event in entry.get("messaging") or []:
                    if "message" not in msg_event:
                        continue
                    sender = msg_event.get("sender") or {}
                    message = msg_event.get("message") or {}
                    Inbox._handle_inbound(
                        platform="messenger",
                        external_id=sender.get("id") or "",
                        content=message.get("text") or "",
                        external_msg_id=message.get("mid"),
                        account_id=account.id if account else False,
                    )
        except Exception:
            _logger.exception("Messenger webhook: erreur traitement")
            return request.make_response('{"ok": false}', status=500)
        return request.make_response(
            json.dumps({"ok": True}),
            headers=[("Content-Type", "application/json")],
        )

    @http.route("/doorway/social/webhook/messenger", type="http", auth="public", csrf=False, methods=["GET"])
    def webhook_messenger_verify(self, **kwargs):
        token = request.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.messenger_webhook_verify_token"
        ) or "doorway_ms_2026"
        mode = kwargs.get("hub.mode")
        challenge = kwargs.get("hub.challenge")
        verify = kwargs.get("hub.verify_token")
        if mode == "subscribe" and verify == token:
            return challenge or ""
        return "Forbidden"

    @http.route("/doorway/social/oauth/<string:platform>", type="http", auth="user", csrf=False)
    def oauth_start(self, platform, account_id=None, **kwargs):
        """Point d'entrée OAuth — à compléter par plateforme."""
        if platform == "tiktok":
            qs = "account_id=%s" % (account_id or "")
            return request.redirect("/doorway/publication/tiktok/oauth/start?%s" % qs)
        return request.make_response(
            f"<h1>OAuth {platform}</h1><p>Compte #{account_id} — configuration API requise.</p>",
            headers=[("Content-Type", "text/html")],
        )
