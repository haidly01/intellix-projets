# -*- coding: utf-8 -*-
"""Reddit OAuth — lecture fil et publication de commentaires."""
import base64
import hashlib
import logging
import re
import secrets
from urllib.parse import urlencode

import requests

from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

OAUTH_AUTHORIZE_URL = "https://www.reddit.com/api/v1/authorize"
OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_API_BASE = "https://oauth.reddit.com"
OAUTH_SCOPES = "identity,read,submit,vote"
REQUEST_TIMEOUT = 25
POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)/", re.I)


class RedditService:
    def __init__(self, env):
        self.env = env

    def _user_agent(self, config):
        return (
            (config.reddit_user_agent or "").strip()
            or "IntellixCRM/1.0 by agencedoorway"
        )

    def credentials_ok(self, config):
        client_id = (config.reddit_client_id or "").strip()
        client_secret = (config.reddit_client_secret or "").strip()
        if not client_id or not client_secret:
            return False
        refresh = (config.reddit_refresh_token or "").strip()
        username = (config.reddit_username or "").strip()
        password = (config.reddit_password or "").strip()
        return bool(refresh or (username and password))

    def _oauth_error_message(self, response, body):
        """Message lisible depuis la réponse Reddit OAuth."""
        if isinstance(body, dict):
            msg = body.get("message") or body.get("error_description")
            err = body.get("error")
            if response.status_code == 400:
                detail = ""
                if err and not str(err).isdigit():
                    detail = " (%s)" % err
                elif msg and str(msg).lower() not in ("bad request", "400"):
                    detail = " (%s)" % msg
                return (
                    "Requête OAuth refusée (400)%s. Vérifiez : app Reddit « web app », "
                    "redirect URI identique dans reddit.com/prefs/apps, et relancez "
                    "« Connecter via Reddit » pour un nouveau code."
                ) % detail
            if response.status_code == 401:
                return "Client ID / secret Reddit incorrects (401)."
            if response.status_code == 403:
                detail = ""
                if isinstance(body, dict):
                    detail = body.get("error_description") or body.get("message") or ""
                return "Accès Reddit refusé (403)%s." % (
                    " — %s" % detail if detail else ""
                )
            if msg and err and str(err) != str(msg):
                return "%s (%s)" % (msg, err)
            if msg:
                return str(msg)[:500]
            if err and not str(err).isdigit():
                return str(err)[:500]
        return (response.text or "HTTP %s" % response.status_code)[:500]

    def _access_token(self, config, allow_password_fallback=True):
        client_id = (config.reddit_client_id or "").strip()
        client_secret = (config.reddit_client_secret or "").strip()
        if not client_id or not client_secret:
            return {"ok": False, "message": "Client ID / secret Reddit manquants."}

        refresh = (config.reddit_refresh_token or "").strip()
        username = (config.reddit_username or "").strip()
        password = (config.reddit_password or "").strip()

        attempts = []
        if refresh:
            attempts.append(
                (
                    "refresh_token",
                    {"grant_type": "refresh_token", "refresh_token": refresh},
                )
            )
        if username and password:
            attempts.append(
                (
                    "password",
                    {
                        "grant_type": "password",
                        "username": username,
                        "password": password,
                    },
                )
            )
        if not attempts:
            return {
                "ok": False,
                "message": (
                    "Refresh token invalide ou absent — renseignez le mot de passe "
                    "Reddit puis cliquez « Obtenir refresh token »."
                ),
            }

        last_error = ""
        for idx, (grant, data) in enumerate(attempts):
            if grant == "password" and not allow_password_fallback and idx > 0:
                continue
            try:
                response = requests.post(
                    OAUTH_TOKEN_URL,
                    auth=(client_id, client_secret),
                    data=data,
                    headers={"User-Agent": self._user_agent(config)},
                    timeout=REQUEST_TIMEOUT,
                )
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                if response.status_code < 400 and body.get("access_token"):
                    new_refresh = body.get("refresh_token")
                    if grant == "password" and new_refresh:
                        config.sudo().write({"reddit_refresh_token": new_refresh})
                    elif grant == "password" and not new_refresh:
                        _logger.warning("Reddit password grant: pas de refresh_token")
                    return {
                        "ok": True,
                        "token": body["access_token"],
                        "refresh_token": new_refresh,
                        "grant": grant,
                    }
                last_error = self._oauth_error_message(response, body)
                if grant == "refresh_token" and username and password:
                    _logger.info(
                        "Reddit refresh_token échoué (%s), essai password.",
                        last_error,
                    )
                    continue
                return {"ok": False, "message": last_error, "grant": grant}
            except requests.RequestException as exc:
                _logger.warning("Reddit OAuth: %s", exc)
                return {"ok": False, "message": str(exc)}
        return {"ok": False, "message": last_error or "OAuth Reddit échoué."}

    def _auth_headers(self, config, token):
        return {
            "Authorization": "Bearer %s" % token,
            "User-Agent": self._user_agent(config),
        }

    @staticmethod
    def extract_post_id(url):
        match = POST_ID_RE.search(url or "")
        return match.group(1) if match else False

    @staticmethod
    def to_thing_id(reddit_id, kind="t3"):
        if not reddit_id:
            return False
        rid = str(reddit_id)
        if rid.startswith(("t1_", "t3_")):
            return rid
        prefix = "t1" if kind == "t1" else "t3"
        return "%s_%s" % (prefix, rid)

    def get_redirect_uri(self, config):
        custom = (config.reddit_oauth_redirect_uri or "").strip().rstrip("/")
        if custom:
            return custom
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
            .strip()
            .rstrip("/")
        )
        return "%s/doorway/veille/reddit/oauth/callback" % base

    @staticmethod
    def generate_pkce():
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def store_oauth_state(self, state, uid, config):
        """Enregistre la session OAuth en table partagée (jamais en mémoire process)."""
        State = self.env["doorway.reddit.oauth.state"].sudo()
        State.cleanup_expired()
        redirect_uri = self.get_redirect_uri(config)
        rec = State.create(
            {
                "state": state,
                "user_id": uid or False,
                "config_id": config.id,
                "code_verifier": False,
                "code_challenge": False,
                "redirect_uri": redirect_uri,
                "client_id": (config.reddit_client_id or "").strip(),
                "client_secret": (config.reddit_client_secret or "").strip(),
            }
        )
        self.env.flush_all()
        self.env.cr.commit()
        _logger.info(
            "Reddit OAuth session %s stored (redirect=%s)",
            rec.id,
            redirect_uri,
        )
        return rec

    def load_oauth_session(self, state):
        """Charge la session. Retourne (record, error) avec error in {None, missing, expired, consumed}."""
        State = self.env["doorway.reddit.oauth.state"].sudo()
        token = (state or "").strip()
        if not token:
            return None, "missing"
        rec = State.search([("state", "=", token)], limit=1)
        if rec:
            if rec.is_expired():
                rec.unlink()
                self.env.flush_all()
                return None, "expired"
            if rec.consumed:
                return rec, "consumed"
            return rec, None
        State.cleanup_expired()
        return None, "missing"

    def build_authorize_url(self, config, session):
        client_id = (session.client_id or config.reddit_client_id or "").strip()
        if not client_id:
            return False
        redirect_uri = (session.redirect_uri or self.get_redirect_uri(config) or "").strip()
        query = {
            "client_id": client_id,
            "response_type": "code",
            "state": session.state,
            "redirect_uri": redirect_uri,
            "duration": "permanent",
            "scope": OAUTH_SCOPES,
        }
        return "%s?%s" % (OAUTH_AUTHORIZE_URL, urlencode(query))

    def _write_config_vals(self, config, vals):
        """Écrit les champs groupés même depuis le callback public."""
        config.sudo().with_user(SUPERUSER_ID).write(vals)

    def exchange_authorization_code(self, config, code, session=None):
        if session:
            client_id = (session.client_id or "").strip() or (
                config.reddit_client_id or ""
            ).strip()
            client_secret = (session.client_secret or "").strip() or (
                config.reddit_client_secret or ""
            ).strip()
            redirect_uri = (session.redirect_uri or "").strip() or self.get_redirect_uri(
                config
            )
            code_verifier = (session.code_verifier or "").strip()
        else:
            client_id = (config.reddit_client_id or "").strip()
            client_secret = (config.reddit_client_secret or "").strip()
            redirect_uri = self.get_redirect_uri(config)
            code_verifier = ""
        if not client_id or not client_secret:
            return {"ok": False, "message": "Client ID / secret Reddit manquants."}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        try:
            response = requests.post(
                OAUTH_TOKEN_URL,
                auth=(client_id, client_secret),
                data=data,
                headers={"User-Agent": self._user_agent(config)},
                timeout=REQUEST_TIMEOUT,
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.status_code >= 400 or not body.get("access_token"):
                msg = self._oauth_error_message(response, body)
                _logger.warning(
                    "Reddit token exchange failed HTTP %s redirect=%s pkce=%s msg=%s body=%s",
                    response.status_code,
                    redirect_uri,
                    bool(code_verifier),
                    msg,
                    (response.text or "")[:300],
                )
                return {"ok": False, "message": msg}
            refresh = body.get("refresh_token")
            if not refresh:
                return {
                    "ok": False,
                    "message": "Reddit n'a pas renvoyé de refresh token (duration=permanent requis).",
                }
            token = body["access_token"]
            username = False
            try:
                me_resp = requests.get(
                    "%s/api/v1/me" % OAUTH_API_BASE,
                    headers=self._auth_headers(config, token),
                    timeout=REQUEST_TIMEOUT,
                )
                me = me_resp.json()
                if me_resp.status_code < 400:
                    username = me.get("name")
            except requests.RequestException:
                pass
            vals = {
                "reddit_refresh_token": refresh,
                "reddit_password": False,
            }
            if username:
                vals["reddit_username"] = username
            self._write_config_vals(config, vals)
            msg = "Refresh token enregistré"
            if username:
                msg += " pour u/%s" % username
            msg += "."
            return {"ok": True, "message": msg, "username": username}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def obtain_refresh_token(self, config):
        """Obtient un refresh token via grant password (app script Reddit)."""
        username = (config.reddit_username or "").strip()
        password = (config.reddit_password or "").strip()
        if not username or not password:
            return {
                "ok": False,
                "message": "Nom d'utilisateur et mot de passe Reddit requis.",
            }
        token_result = self._access_token(config)
        if not token_result.get("ok"):
            return token_result
        refresh = token_result.get("refresh_token")
        if not refresh:
            return {
                "ok": False,
                "message": "Reddit n'a pas renvoyé de refresh token (vérifiez le type d'app « script »).",
            }
        config.sudo().write({"reddit_refresh_token": refresh})
        return {
            "ok": True,
            "message": "Refresh token enregistré pour u/%s." % username,
            "refresh_token": refresh,
        }

    def validate_config(self, config):
        result = {"ok": False, "username": False, "messages": []}
        if not self.credentials_ok(config):
            result["messages"].append(
                "Renseignez client ID, secret et compte Reddit (ou refresh token)."
            )
            return result

        token_result = self._access_token(config)
        if not token_result.get("ok"):
            msg = token_result.get("message") or "?"
            hint = ""
            if (config.reddit_refresh_token or "").strip() and not (
                config.reddit_password or ""
            ).strip():
                hint = (
                    " Le refresh token enregistré semble invalide : saisissez le mot de "
                    "passe Reddit et utilisez « Obtenir refresh token »."
                )
            result["messages"].append("OAuth Reddit : %s.%s" % (msg, hint))
            return result

        token = token_result["token"]
        try:
            response = requests.get(
                "%s/api/v1/me" % OAUTH_API_BASE,
                headers=self._auth_headers(config, token),
                timeout=REQUEST_TIMEOUT,
            )
            me = response.json()
            if response.status_code >= 400:
                result["messages"].append(
                    "Profil Reddit : %s" % (me.get("message") or response.text[:200])
                )
                return result
            result["ok"] = True
            result["username"] = me.get("name")
            result["messages"].append(
                "Reddit : connecté en tant que u/%s." % (me.get("name") or "?")
            )
        except requests.RequestException as exc:
            result["messages"].append("Profil Reddit : %s" % exc)
        return result

    def fetch_thread(self, config, signal):
        url = (signal.url or "").split("?")[0].rstrip("/")
        post_id = self.extract_post_id(url)
        if not post_id:
            return {"ok": False, "message": "URL Reddit invalide.", "messages": []}

        if self.credentials_ok(config):
            token_result = self._access_token(config)
            if token_result.get("ok"):
                return self._fetch_thread_oauth(
                    config, token_result["token"], url, post_id
                )

        return self._fetch_thread_public(url)

    def _fetch_thread_oauth(self, config, token, url, post_id):
        json_url = "%s/comments/%s.json" % (OAUTH_API_BASE, post_id)
        try:
            response = requests.get(
                json_url,
                headers=self._auth_headers(config, token),
                timeout=REQUEST_TIMEOUT,
                params={"limit": 50, "depth": 3, "sort": "new"},
            )
            if response.status_code != 200:
                return {
                    "ok": False,
                    "message": "Reddit HTTP %s" % response.status_code,
                    "messages": [],
                }
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": str(exc), "messages": []}
        messages = self._parse_listing(data, post_id)
        return {"ok": True, "messages": messages}

    def _fetch_thread_public(self, url):
        json_url = url if url.endswith(".json") else url + ".json"
        try:
            response = requests.get(
                json_url,
                headers={"User-Agent": "IntellixCRM/1.0"},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                return {
                    "ok": False,
                    "message": "Reddit public HTTP %s" % response.status_code,
                    "messages": [],
                }
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": str(exc), "messages": []}
        post_id = self.extract_post_id(url)
        messages = self._parse_listing(data, post_id)
        return {"ok": bool(messages), "messages": messages}

    def _parse_listing(self, data, post_id):
        messages = []
        try:
            post_listing = data[0]["data"]["children"][0]["data"]
            messages.append(
                {
                    "external_id": post_listing.get("id") or post_id,
                    "author_name": "u/%s" % (post_listing.get("author") or "reddit"),
                    "body": (post_listing.get("title") or "")
                    + "\n"
                    + (post_listing.get("selftext") or ""),
                    "posted_at": post_listing.get("created_utc"),
                    "direction": "inbound",
                    "platform": "reddit",
                }
            )
            comments = data[1]["data"]["children"] if len(data) > 1 else []
            for child in comments[:50]:
                c = child.get("data") or {}
                if not c.get("body") or c.get("body") == "[deleted]":
                    continue
                messages.append(
                    {
                        "external_id": c.get("id"),
                        "author_name": "u/%s" % (c.get("author") or "reddit"),
                        "body": c.get("body") or "",
                        "posted_at": c.get("created_utc"),
                        "direction": "inbound",
                        "platform": "reddit",
                    }
                )
        except (KeyError, IndexError, TypeError):
            return messages
        return messages

    def send_reply(self, config, signal, message_text):
        text = (message_text or "").strip()
        if not text:
            return {"ok": False, "message": "Message vide."}

        token_result = self._access_token(config)
        if not token_result.get("ok"):
            return token_result

        target = signal._get_reddit_reply_thing_id()
        if not target:
            return {
                "ok": False,
                "message": "Impossible de cibler le post/commentaire Reddit.",
            }

        try:
            response = requests.post(
                "%s/api/comment" % OAUTH_API_BASE,
                headers=self._auth_headers(config, token_result["token"]),
                data={"thing_id": target, "text": text},
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json()
            if response.status_code >= 400:
                errors = body.get("json", {}).get("errors") or []
                if errors:
                    msg = "; ".join(" ".join(map(str, e)) for e in errors)
                else:
                    msg = body.get("message") or response.text[:300]
                return {"ok": False, "message": msg}
            comment_data = (
                (body.get("json") or {}).get("data") or {}
            ).get("things") or []
            external_id = False
            if comment_data:
                thing = comment_data[0].get("data") or {}
                external_id = thing.get("id") or thing.get("name")
            return {
                "ok": True,
                "message": "Commentaire Reddit publié.",
                "external_id": external_id,
                "body": text,
            }
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def vote_up(self, config, signal):
        """Upvote Reddit (réactivation douce)."""
        token_result = self._access_token(config)
        if not token_result.get("ok"):
            return token_result

        thing_id = signal._get_reddit_reply_thing_id()
        if not thing_id:
            post_id = self.extract_post_id(signal.url)
            thing_id = self.to_thing_id(post_id, kind="t3") if post_id else False
        if not thing_id:
            return {"ok": False, "message": "Impossible de cibler le post Reddit."}

        try:
            response = requests.post(
                "%s/api/vote" % OAUTH_API_BASE,
                headers=self._auth_headers(config, token_result["token"]),
                data={"id": thing_id, "dir": 1},
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json() if response.text else {}
            if response.status_code >= 400:
                errors = body.get("json", {}).get("errors") or []
                msg = "; ".join(" ".join(map(str, e)) for e in errors) if errors else response.text[:300]
                return {"ok": False, "message": msg or "Vote Reddit refusé."}
            return {"ok": True, "message": "Upvote Reddit publié.", "external_id": thing_id}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}
