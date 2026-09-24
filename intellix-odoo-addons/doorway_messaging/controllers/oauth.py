# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

import requests

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MessagingOAuthController(http.Controller):
    def _back_url(self):
        base = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
            .rstrip("/")
        )
        return "%s/odoo/action-doorway_messaging.action_message_campaign" % base

    def _result_page(self, ok, message, redirect_url):
        title = "Connexion réussie" if ok else "Connexion échouée"
        color = "#198754" if ok else "#dc3545"
        html = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"/>
<title>%s</title>
<meta http-equiv="refresh" content="4;url=%s"/>
<style>body{font-family:sans-serif;max-width:520px;margin:3rem auto;padding:1rem;}
h1{color:%s;font-size:1.25rem;}p{line-height:1.5;}a{color:#0d6efd;}</style>
</head><body>
<h1>%s</h1>
<p>%s</p>
<p><a href="%s">Retour à Odoo → Messaging</a></p>
</body></html>""" % (
            title,
            redirect_url,
            color,
            title,
            message.replace("<", "&lt;"),
            redirect_url,
        )
        return request.make_response(html, headers=[("Content-Type", "text/html")])

    @http.route(
        "/doorway/messaging/oauth/linkedin/callback",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def linkedin_callback(self, **kwargs):
        env = request.env
        back = self._back_url()
        error = kwargs.get("error")
        if error:
            return self._result_page(False, "LinkedIn: %s" % error, back)
        code = (kwargs.get("code") or "").strip()
        state = (kwargs.get("state") or "").strip()
        if not code or not state:
            return self._result_page(False, "Paramètres OAuth manquants.", back)

        cfg = env["doorway.channel.config"].sudo().search(
            [("canal", "=", "linkedin"), ("oauth_state", "=", state)], limit=1
        )
        if not cfg:
            return self._result_page(False, "Session OAuth expirée.", back)

        icp = env["ir.config_parameter"].sudo()
        client_id = cfg.api_key or icp.get_param(
            "doorway_messaging.linkedin_client_id", ""
        )
        client_secret = cfg.api_secret or icp.get_param(
            "doorway_messaging.linkedin_client_secret", ""
        )
        redirect_uri = "%s/doorway/messaging/oauth/linkedin/callback" % icp.get_param(
            "web.base.url", ""
        ).rstrip("/")

        try:
            r = requests.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=20,
            )
            if r.status_code != 200:
                return self._result_page(False, r.text[:300], back)
            data = r.json()
            cfg.write(
                {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token", cfg.refresh_token),
                    "token_expiry": fields.Datetime.now()
                    + timedelta(seconds=int(data.get("expires_in", 3600))),
                    "oauth_state": False,
                }
            )
            if hasattr(cfg, "action_sync_social_account"):
                cfg.action_sync_social_account()
            return self._result_page(True, "LinkedIn connecté avec succès.", back)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("LinkedIn OAuth")
            return self._result_page(False, str(exc), back)

    @http.route(
        "/doorway/messaging/oauth/google/callback",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def google_callback(self, **kwargs):
        env = request.env
        back = self._back_url()
        error = kwargs.get("error")
        if error:
            return self._result_page(False, "Google: %s" % error, back)
        code = (kwargs.get("code") or "").strip()
        state = (kwargs.get("state") or "").strip()
        if not code or not state:
            return self._result_page(False, "Paramètres OAuth manquants.", back)

        cfg = env["doorway.channel.config"].sudo().search(
            [("canal", "=", "gmb"), ("oauth_state", "=", state)], limit=1
        )
        if not cfg:
            return self._result_page(False, "Session OAuth expirée.", back)

        icp = env["ir.config_parameter"].sudo()
        client_id = cfg.api_key or icp.get_param(
            "doorway_messaging.google_client_id", ""
        )
        client_secret = cfg.api_secret or icp.get_param(
            "doorway_messaging.google_client_secret", ""
        )
        redirect_uri = "%s/doorway/messaging/oauth/google/callback" % icp.get_param(
            "web.base.url", ""
        ).rstrip("/")

        try:
            r = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=20,
            )
            if r.status_code != 200:
                return self._result_page(False, r.text[:300], back)
            data = r.json()
            cfg.write(
                {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token", cfg.refresh_token),
                    "token_expiry": fields.Datetime.now()
                    + timedelta(seconds=int(data.get("expires_in", 3600))),
                    "oauth_state": False,
                }
            )
            if hasattr(cfg, "action_sync_social_account"):
                cfg.action_sync_social_account()
            return self._result_page(True, "Google My Business connecté.", back)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Google OAuth")
            return self._result_page(False, str(exc), back)
