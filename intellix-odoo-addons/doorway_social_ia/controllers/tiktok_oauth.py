# -*- coding: utf-8 -*-
import logging
import secrets

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TiktokOAuthController(http.Controller):
    def _svc(self):
        return request.env["doorway.social.tiktok.service"].sudo()

    def _https_root(self):
        root = (request.httprequest.url_root or "").rstrip("/")
        forwarded = (request.httprequest.headers.get("X-Forwarded-Proto") or "").lower()
        if forwarded == "https" and root.startswith("http://"):
            root = "https://" + root[len("http://") :]
        if root.startswith("http://"):
            root = "https://" + root[len("http://") :]
        return root

    def _result_page(self, ok, message):
        back = "%s/odoo/action-doorway_social_ia.action_social_accounts" % self._https_root()
        title = "TikTok connecté" if ok else "Connexion TikTok échouée"
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
<p><a href="%s">Retour à Odoo → Comptes réseaux</a></p>
</body></html>""" % (
            title,
            back,
            color,
            title,
            (message or "").replace("<", "&lt;"),
            back,
        )
        return request.make_response(html, headers=[("Content-Type", "text/html")])

    @http.route(
        [
            "/doorway/publication/tiktok/oauth/start",
            "/doorway/social/oauth/tiktok",
        ],
        type="http",
        auth="user",
        csrf=False,
    )
    def tiktok_oauth_start(self, account_id=None, **kwargs):
        env = request.env
        svc = self._svc()
        client_key, client_secret = svc.get_app_credentials()
        if not client_key or not client_secret:
            return self._result_page(
                False,
                "Renseignez la Client Key et le Client Secret TikTok "
                "(Paramètres système doorway_social_ia.tiktok_client_key / "
                "tiktok_client_secret) avant de connecter un compte.",
            )
        svc.ensure_brand_tiktok_accounts()
        account = False
        if account_id:
            try:
                account = env["doorway.social.account"].browse(int(account_id))
            except (TypeError, ValueError):
                account = False
            if not account or not account.exists() or account.platform != "tiktok":
                account = False
        pipeline_id = kwargs.get("pipeline_id") or False
        try:
            pipeline_id = int(pipeline_id) if pipeline_id else False
        except (TypeError, ValueError):
            pipeline_id = False
        if not account:
            domain = [("platform", "=", "tiktok")]
            if pipeline_id:
                domain.append(("pipeline_id", "=", pipeline_id))
                account = env["doorway.social.account"].search(domain, limit=1)
        if not account:
            account = env["doorway.social.account"].create(
                {
                    "name": "TikTok — nouveau compte",
                    "platform": "tiktok",
                    "connection_state": "disconnected",
                    "pipeline_id": pipeline_id or False,
                }
            )
        state = secrets.token_hex(16)
        session = svc.store_oauth_state(state, env.uid, account)
        url = svc.build_authorize_url(session)
        if not url:
            return self._result_page(False, "Impossible de construire l'URL OAuth TikTok.")
        return request.redirect(url, local=False)

    @http.route(
        "/doorway/publication/tiktok/oauth/callback",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def tiktok_oauth_callback(self, **kwargs):
        svc = self._svc()
        error = kwargs.get("error") or kwargs.get("error_description")
        if error:
            return self._result_page(False, "TikTok a refusé l'autorisation : %s" % error)
        code = (kwargs.get("code") or "").strip()
        state = (kwargs.get("state") or "").strip()
        if not code or not state:
            return self._result_page(
                False, "Paramètres OAuth TikTok manquants (code ou state)."
            )
        session, err = svc.load_oauth_session(state)
        if err == "missing":
            return self._result_page(
                False,
                "Session OAuth introuvable — relancez « Connecter un compte TikTok ».",
            )
        if err == "expired":
            return self._result_page(
                False,
                "Session OAuth expirée (délai de 10 minutes dépassé) — relancez la connexion.",
            )
        if err == "consumed":
            if session.result == "ok":
                return self._result_page(
                    True, session.result_message or "Compte TikTok déjà connecté."
                )
            return self._result_page(
                False,
                session.result_message
                or "Cette autorisation a déjà été utilisée. Relancez la connexion.",
            )
        if not session.lock_row():
            return self._result_page(
                False, "Session OAuth introuvable — relancez la connexion TikTok."
            )
        if session.consumed:
            if session.result == "ok":
                return self._result_page(
                    True, session.result_message or "Compte TikTok déjà connecté."
                )
            return self._result_page(
                False,
                session.result_message or "Cette autorisation a déjà été utilisée.",
            )
        result = svc.exchange_code(code, session)
        if not result.get("ok"):
            msg = result.get("message") or "Échec OAuth TikTok."
            session.sudo().write(
                {"consumed": True, "result": "error", "result_message": msg[:500]}
            )
            return self._result_page(False, msg)
        account = session.account_id.sudo()
        if not account:
            return self._result_page(False, "Compte TikTok introuvable après OAuth.")
        svc.apply_oauth_tokens(account, result)
        msg = "Compte TikTok connecté."
        if result.get("username"):
            msg = "Compte TikTok connecté : %s." % result["username"]
        session.sudo().write(
            {"consumed": True, "result": "ok", "result_message": msg[:500]}
        )
        return self._result_page(True, msg)
