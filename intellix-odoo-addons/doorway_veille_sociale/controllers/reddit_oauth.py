# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RedditOAuthController(http.Controller):
    @http.route(
        "/doorway/veille/reddit/oauth/callback",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def reddit_oauth_callback(self, **kwargs):
        from odoo.addons.doorway_veille_sociale.services.reddit_service import (
            RedditService,
        )

        env = request.env
        back = self._back_url(env)

        error = kwargs.get("error")
        if error:
            return self._result_page(
                False,
                "Reddit a refusé l'autorisation : %s" % error,
                back,
            )

        code = (kwargs.get("code") or "").strip()
        # Reddit ajoute parfois #_ en fin de code dans l'URL
        if code:
            code = code.split("#")[0].strip()
        state = (kwargs.get("state") or "").strip()
        if not code or not state:
            return self._result_page(
                False, "Paramètres OAuth Reddit manquants (code ou state).", back
            )

        svc = RedditService(env)
        session, err = svc.load_oauth_session(state)
        if err == "missing":
            return self._result_page(
                False,
                "Session OAuth introuvable — relancez « Connecter via Reddit » dans Odoo.",
                back,
            )
        if err == "expired":
            return self._result_page(
                False,
                "Session OAuth expirée (délai de 10 minutes dépassé) — relancez « Connecter via Reddit ».",
                back,
            )
        if err == "consumed":
            if session.result == "ok":
                return self._result_page(
                    True,
                    session.result_message or "Compte Reddit déjà connecté.",
                    back,
                )
            return self._result_page(
                False,
                session.result_message
                or "Cette autorisation a déjà été utilisée. Relancez « Connecter via Reddit ».",
                back,
            )

        if not session.lock_row():
            return self._result_page(
                False,
                "Session OAuth introuvable — relancez « Connecter via Reddit » dans Odoo.",
                back,
            )
        if session.consumed:
            if session.result == "ok":
                return self._result_page(
                    True,
                    session.result_message or "Compte Reddit déjà connecté.",
                    back,
                )
            return self._result_page(
                False,
                session.result_message
                or "Cette autorisation a déjà été utilisée. Relancez « Connecter via Reddit ».",
                back,
            )

        cfg = (
            session.config_id
            or env["doorway.veille.config"].sudo().with_user(SUPERUSER_ID).get_config()
        )
        cfg = cfg.sudo().with_user(SUPERUSER_ID)
        result = svc.exchange_authorization_code(cfg, code, session=session)
        if not result.get("ok"):
            fail_msg = result.get("message") or "Échec OAuth."
            session.sudo().write(
                {
                    "consumed": True,
                    "result": "error",
                    "result_message": fail_msg[:500],
                }
            )
            return self._result_page(False, fail_msg, back)

        test = svc.validate_config(cfg)
        svc._write_config_vals(
            cfg,
            {
                "reddit_last_check": fields.Datetime.now(),
                "reddit_status_message": "\n".join(test.get("messages") or []),
                "reddit_actif": test.get("ok", False),
            },
        )
        try:
            cfg._run_reddit_n8n_sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Reddit n8n sync after OAuth: %s", exc)

        msg = result.get("message") or "Compte Reddit connecté."
        if test.get("messages"):
            msg += " " + " ".join(test["messages"])
        session.sudo().write(
            {
                "consumed": True,
                "result": "ok",
                "result_message": msg[:500],
            }
        )
        return self._result_page(True, msg, back)

    def _back_url(self, env):
        root = (request.httprequest.url_root or "").rstrip("/")
        forwarded = (request.httprequest.headers.get("X-Forwarded-Proto") or "").lower()
        if forwarded == "https" and root.startswith("http://"):
            root = "https://" + root[len("http://") :]
        if not root:
            root = (
                env["ir.config_parameter"].sudo().get_param("web.base.url", "") or ""
            ).rstrip("/")
            if root.startswith("http://"):
                root = "https://" + root[len("http://") :]
        return "%s/web#action=doorway_veille_sociale.action_veille_sources_open" % root

    def _result_page(self, ok, message, redirect_url):
        title = "Reddit connecté" if ok else "Connexion Reddit échouée"
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
<p><a href="%s">Retour à Odoo → Connexions &amp; sources</a></p>
</body></html>""" % (
            title,
            redirect_url,
            color,
            title,
            message.replace("<", "&lt;"),
            redirect_url,
        )
        return request.make_response(html, headers=[("Content-Type", "text/html")])
