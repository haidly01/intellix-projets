# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import time

from odoo import http
from odoo.http import request
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

ROUTES = [
    "/web/doorway-enter",
    "/en/web/doorway-enter",
    "/fr/web/doorway-enter",
    "/fr_CA/web/doorway-enter",
]


def _secret():
    return request.env["ir.config_parameter"].sudo().get_param("database.secret") or "intellix"


def check_token(token):
    try:
        uid_s, exp_s, sig = (token or "").split(":")
        uid = int(uid_s)
        exp = int(exp_s)
    except Exception:
        return None
    if exp < int(time.time()):
        return None
    payload = "%s:%s" % (uid, exp)
    expect = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expect, sig):
        return None
    return uid


def _nocache_headers():
    return [
        ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
        ("Pragma", "no-cache"),
        ("CDN-Cache-Control", "no-store"),
        ("Content-Type", "text/html; charset=utf-8"),
    ]


class DoorwayMagicLogin(http.Controller):
    def _unlock_user(self, token):
        uid = check_token(token or "")
        if not uid:
            return None
        user = request.env["res.users"].sudo().browse(uid)
        if not user.exists() or not user.active or user.share:
            return None
        request.session.uid = None
        request.session["pre_login"] = user.login
        request.session["pre_uid"] = user.id
        request.session.finalize(request.env(user=None))
        request.update_env(user=request.session.uid)
        _logger.warning("IX_UNLOCK ok uid=%s login=%s", user.id, user.login)
        return user

    @http.route(ROUTES, type="http", auth="public", sitemap=False, csrf=False, methods=["GET"])
    def doorway_enter_get(self, token=None, **kw):
        """GET shows a button — WhatsApp preview cannot POST/login."""
        token = token or ""
        ok = bool(check_token(token))
        if not ok:
            html = (
                "<!doctype html><meta charset=utf-8><title>Lien invalide</title>"
                "<body style='font-family:sans-serif;padding:40px;background:#111;color:#fff'>"
                "<h1>Lien invalide ou expire</h1>"
                "<p>Demandez un nouveau lien.</p></body>"
            )
            return request.make_response(html, headers=_nocache_headers())
        tok = html_escape(token)
        html = (
            "<!doctype html><html><head><meta charset=utf-8>"
            "<meta name='robots' content='noindex'>"
            "<title>Entrer dans IntelliX</title></head>"
            "<body style='font-family:system-ui,sans-serif;padding:48px;background:#0b0b16;color:#fff;text-align:center'>"
            "<h1 style='color:#f59e0b'>IntelliX CRM</h1>"
            "<p>Clique le bouton ci-dessous pour te connecter (compte Zakaria).</p>"
            "<form method='POST' action='/web/doorway-enter'>"
            "<input type='hidden' name='token' value='%s'/>"
            "<button type='submit' style='margin-top:20px;padding:16px 28px;font-size:18px;font-weight:700;"
            "background:#f59e0b;color:#111;border:0;border-radius:10px;cursor:pointer'>"
            "Entrer dans IntelliX</button></form>"
            "<p style='margin-top:24px;color:#888;font-size:13px'>Ouvre ce lien dans Chrome (pas dans WhatsApp).</p>"
            "</body></html>"
        ) % tok
        return request.make_response(html, headers=_nocache_headers())

    @http.route(ROUTES, type="http", auth="public", sitemap=False, csrf=False, methods=["POST"])
    def doorway_enter_post(self, token=None, **kw):
        user = self._unlock_user(token)
        if not user:
            return request.redirect("/web/login")
        return request.redirect("/odoo")
