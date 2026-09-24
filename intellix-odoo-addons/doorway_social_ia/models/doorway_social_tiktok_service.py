# -*- coding: utf-8 -*-
"""TikTok Login Kit + Content Posting API (Direct Post)."""
import logging
import os
import subprocess
import tempfile
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TIKTOK_VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_SCOPES = "user.info.basic,video.publish"
OFFICIAL_REDIRECT_URI = (
    "https://intellixcrm.com/doorway/publication/tiktok/oauth/callback"
)
REQUEST_TIMEOUT = 45
MAX_VIDEO_BYTES = 256 * 1024 * 1024
MIN_DURATION_SEC = 3
DEFAULT_MAX_DURATION_SEC = 600
ALLOWED_MIMES = (
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
)
ICP_KEY = "doorway_social_ia.tiktok_client_key"
ICP_SECRET = "doorway_social_ia.tiktok_client_secret"


class DoorwaySocialTiktokService(models.AbstractModel):
    _name = "doorway.social.tiktok.service"
    _description = "Publication TikTok (Content Posting API)"

    def get_app_credentials(self):
        icp = self.env["ir.config_parameter"].sudo()
        key = (icp.get_param(ICP_KEY) or "").strip()
        secret = (icp.get_param(ICP_SECRET) or "").strip()
        return key, secret

    def set_app_credentials(self, client_key, client_secret):
        icp = self.env["ir.config_parameter"].sudo()
        if client_key:
            icp.set_param(ICP_KEY, client_key.strip())
        if client_secret:
            icp.set_param(ICP_SECRET, client_secret.strip())
        return True

    def get_redirect_uri(self):
        icp = self.env["ir.config_parameter"].sudo()
        override = (icp.get_param("doorway_social_ia.tiktok_redirect_uri") or "").strip()
        if override:
            return override
        return OFFICIAL_REDIRECT_URI

    def store_oauth_state(self, state, uid, account):
        State = self.env["doorway.tiktok.oauth.state"].sudo()
        State.cleanup_expired()
        client_key, client_secret = self.get_app_credentials()
        rec = State.create(
            {
                "state": state,
                "user_id": uid or False,
                "account_id": account.id,
                "redirect_uri": self.get_redirect_uri(),
                "client_key": client_key,
                "client_secret": client_secret,
            }
        )
        self.env.flush_all()
        self.env.cr.commit()
        return rec

    def load_oauth_session(self, state):
        State = self.env["doorway.tiktok.oauth.state"].sudo()
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

    def build_authorize_url(self, session):
        from urllib.parse import quote

        client_key = (session.client_key or self.get_app_credentials()[0] or "").strip()
        if not client_key:
            return False
        redirect_uri = (session.redirect_uri or self.get_redirect_uri() or "").strip()
        # TikTok docs leave the comma in scope unencoded. urlencode() turns it
        # into %2C and the authorize page then flags client_key.
        query = (
            "client_key=%s&response_type=code&scope=%s&redirect_uri=%s&state=%s"
            % (
                quote(client_key, safe=""),
                quote(TIKTOK_SCOPES, safe=","),
                quote(redirect_uri, safe=""),
                quote(session.state or "", safe=""),
            )
        )
        return "%s?%s" % (TIKTOK_AUTH_URL, query)

    def exchange_code(self, code, session):
        client_key, client_secret = self.get_app_credentials()
        client_key = (session.client_key or client_key or "").strip()
        client_secret = (session.client_secret or client_secret or "").strip()
        if not client_key or not client_secret:
            return {"ok": False, "message": "Client key / secret TikTok manquants."}
        try:
            response = requests.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": session.redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=REQUEST_TIMEOUT,
            )
            body = {}
            try:
                body = response.json()
            except ValueError:
                body = {}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}
        # TikTok v2 token endpoint returns fields at top level (not nested in data).
        access = body.get("access_token")
        if not access:
            err = body.get("error_description") or body.get("error") or body.get("message")
            if isinstance(body.get("error"), dict):
                err = body["error"].get("message") or err
            return {
                "ok": False,
                "message": err or "Échange du code TikTok refusé (HTTP %s)." % response.status_code,
            }
        expires_in = int(body.get("expires_in") or 86400)
        expiry = fields.Datetime.now() + timedelta(seconds=max(expires_in - 60, 60))
        open_id = body.get("open_id") or ""
        refresh = body.get("refresh_token") or ""
        username = self._fetch_username(access) or open_id
        return {
            "ok": True,
            "access_token": access,
            "refresh_token": refresh,
            "open_id": open_id,
            "token_expiry": expiry,
            "username": username,
        }

    def _fetch_username(self, access_token):
        try:
            response = requests.get(
                TIKTOK_USER_INFO_URL,
                params={"fields": "open_id,display_name,username,avatar_url"},
                headers={"Authorization": "Bearer %s" % access_token},
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json()
            user = (body.get("data") or {}).get("user") or {}
            return user.get("display_name") or user.get("username") or False
        except (requests.RequestException, ValueError, TypeError):
            return False

    def refresh_account_token(self, account):
        """Rafraîchit le token si proche de l'expiration. Retourne le bearer ou False."""
        account = account.sudo()
        token = (account.tiktok_access_token or account.access_token or "").strip()
        refresh = (account.tiktok_refresh_token or account.refresh_token or "").strip()
        expiry = account.token_expiry
        now = fields.Datetime.now()
        still_valid = token and (not expiry or expiry > now)
        if still_valid and expiry and (expiry - now).total_seconds() > 300:
            return token
        if not refresh:
            return token or False
        client_key, client_secret = self.get_app_credentials()
        if not client_key or not client_secret:
            return token or False
        try:
            response = requests.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning("TikTok refresh token: %s", exc)
            return token or False
        access = body.get("access_token")
        if not access:
            _logger.warning("TikTok refresh failed: %s", body)
            account.write({"connection_state": "expired"})
            return False
        expires_in = int(body.get("expires_in") or 86400)
        vals = {
            "tiktok_access_token": access,
            "access_token": access,
            "token_expiry": fields.Datetime.now()
            + timedelta(seconds=max(expires_in - 60, 60)),
            "connection_state": "connected",
        }
        if body.get("refresh_token"):
            vals["tiktok_refresh_token"] = body["refresh_token"]
            vals["refresh_token"] = body["refresh_token"]
        if body.get("open_id"):
            vals["tiktok_open_id"] = body["open_id"]
            vals["external_account_id"] = body["open_id"]
        account.write(vals)
        return access

    def apply_oauth_tokens(self, account, token_data):
        username = token_data.get("username")
        name = account.name
        if username and "TikTok" in (account.name or ""):
            pipeline = account.pipeline_id.display_name if account.pipeline_id else ""
            name = "%s — TikTok (@%s)" % (pipeline or "TikTok", username)
            if not pipeline:
                name = "TikTok — %s" % username
        handle = (username or "").strip().lstrip("@")
        account.sudo().write(
            {
                "name": name,
                "tiktok_username": handle or account.tiktok_username,
                "tiktok_open_id": token_data.get("open_id"),
                "tiktok_access_token": token_data.get("access_token"),
                "tiktok_refresh_token": token_data.get("refresh_token"),
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_expiry": token_data.get("token_expiry"),
                "external_account_id": token_data.get("open_id"),
                "connection_state": "connected",
            }
        )
        return True

    def ensure_brand_tiktok_accounts(self):
        """Crée un compte TikTok par marque (Coins Marocain, Coins Québec)."""
        Account = self.env["doorway.social.account"].sudo()
        Team = self.env["crm.team"].sudo()
        specs = (
            ("Coins Marocain — TikTok", "Coins Marocain", 9, "coinsmarrakech"),
            ("Coins Québec — TikTok", "Coins Québec", 109, False),
        )
        created = Account.browse()
        for name, team_name, preferred_id, handle in specs:
            existing = Account.search(
                [("platform", "=", "tiktok"), ("name", "=", name)], limit=1
            )
            team = Team.browse(preferred_id)
            if not team.exists():
                team = Team.search([("name", "=", team_name)], limit=1)
            if existing:
                vals = {}
                if team and not existing.pipeline_id:
                    vals["pipeline_id"] = team.id
                if handle and not existing.tiktok_username:
                    vals["tiktok_username"] = handle
                if vals:
                    existing.write(vals)
                continue
            domain = [("platform", "=", "tiktok")]
            if team:
                domain.append(("pipeline_id", "=", team.id))
                existing = Account.search(domain, limit=1)
            if existing:
                if handle and not existing.tiktok_username:
                    existing.write({"tiktok_username": handle})
                continue
            created |= Account.create(
                {
                    "name": name,
                    "platform": "tiktok",
                    "connection_state": "disconnected",
                    "pipeline_id": team.id if team else False,
                    "tiktok_username": handle or False,
                }
            )
        return created

    def _bearer_headers(self, token):
        return {
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json; charset=UTF-8",
        }

    def query_creator_info(self, token):
        try:
            response = requests.post(
                TIKTOK_CREATOR_INFO_URL,
                headers=self._bearer_headers(token),
                json={},
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": str(exc)}
        err = body.get("error") or {}
        if err.get("code") not in ("ok", None, ""):
            return {
                "ok": False,
                "message": err.get("message") or err.get("code") or "creator_info refusé",
            }
        return {"ok": True, "data": body.get("data") or {}}

    def _pick_privacy(self, creator, post):
        options = creator.get("privacy_level_options") or []
        # Sandbox / app non auditée : SELF_ONLY uniquement.
        if "SELF_ONLY" in options:
            return "SELF_ONLY"
        if post.privacy == "limited" and "MUTUAL_FOLLOW_FRIENDS" in options:
            return "MUTUAL_FOLLOW_FRIENDS"
        if "PUBLIC_TO_EVERYONE" in options:
            return "PUBLIC_TO_EVERYONE"
        if options:
            return options[0]
        return "SELF_ONLY"

    def _video_bytes_and_meta(self, post):
        media = [m for m in post._collect_media() if m.get("is_video")]
        if not media:
            raise UserError(
                _(
                    "TikTok exige une vidéo (mp4 / mov / webm). "
                    "Ajoutez un fichier dans Médias, ou une URL vidéo HeyGen."
                )
            )
        item = media[0]
        att = item.get("attachment")
        data = b""
        mimetype = item.get("mimetype") or "video/mp4"
        filename = "video.mp4"
        if att:
            import base64

            b64 = att.sudo().datas
            if b64:
                data = base64.b64decode(b64)
            filename = att.name or filename
            mimetype = (att.mimetype or mimetype).lower()
        if not data and item.get("public_url"):
            try:
                resp = requests.get(item["public_url"], timeout=REQUEST_TIMEOUT, stream=True)
                resp.raise_for_status()
                data = resp.content
                mimetype = (resp.headers.get("Content-Type") or mimetype).split(";")[0].strip()
            except requests.RequestException as exc:
                raise UserError(_("Impossible de télécharger la vidéo : %s") % exc) from exc
        if not data:
            raise UserError(_("Fichier vidéo vide ou illisible."))
        if len(data) > MAX_VIDEO_BYTES:
            raise UserError(
                _("Vidéo trop lourde (%s Mo). Maximum %s Mo.")
                % (round(len(data) / 1048576, 1), MAX_VIDEO_BYTES // 1048576)
            )
        if mimetype not in ALLOWED_MIMES and not filename.lower().endswith(
            (".mp4", ".mov", ".webm", ".m4v")
        ):
            raise UserError(
                _("Format TikTok non supporté (%s). Utilisez MP4, MOV ou WebM.") % mimetype
            )
        duration = self._probe_duration(data, filename)
        return data, mimetype, filename, duration

    def _probe_duration(self, data, filename):
        suffix = os.path.splitext(filename or "")[1] or ".mp4"
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data)
                path = tmp.name
            try:
                proc = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return float(proc.stdout.strip())
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            _logger.info("ffprobe indisponible : %s", exc)
        return False

    def validate_video(self, post, creator=None):
        data, mimetype, filename, duration = self._video_bytes_and_meta(post)
        max_dur = DEFAULT_MAX_DURATION_SEC
        if creator and creator.get("max_video_post_duration_sec"):
            max_dur = int(creator["max_video_post_duration_sec"])
        if duration is not False:
            if duration < MIN_DURATION_SEC:
                raise UserError(
                    _("Vidéo trop courte (%.1f s). TikTok exige au moins %s secondes.")
                    % (duration, MIN_DURATION_SEC)
                )
            if duration > max_dur:
                raise UserError(
                    _("Vidéo trop longue (%.0f s). Maximum %s secondes pour ce compte.")
                    % (duration, max_dur)
                )
        return data, mimetype, filename, duration

    def publish_post(self, post):
        """Initie le Direct Post. Retourne {'pending': True} ou lève UserError."""
        Account = self.env["doorway.social.account"].sudo()
        accounts = post.account_ids.filtered(
            lambda a: a.platform == "tiktok" and a.connection_state == "connected"
        )
        if not accounts:
            domain = [("platform", "=", "tiktok"), ("connection_state", "=", "connected")]
            if post.pipeline_id:
                domain.append(("pipeline_id", "=", post.pipeline_id.id))
            accounts = Account.search(domain)
        if not accounts:
            raise UserError(
                _(
                    "Aucun compte TikTok connecté pour cette marque. "
                    "Ouvrez Comptes → Connecter un compte TikTok."
                )
            )
        account = accounts[0]
        token = self.refresh_account_token(account)
        if not token:
            raise UserError(
                _("Token TikTok expiré pour %s — reconnectez le compte.") % account.name
            )
        creator_res = self.query_creator_info(token)
        creator = creator_res.get("data") or {} if creator_res.get("ok") else {}
        data, mimetype, filename, _duration = self.validate_video(post, creator)
        privacy = self._pick_privacy(creator, post)
        title = (post.caption or post.hook or post.name or "")[:2200]
        if post.hashtags and post.hashtags not in title:
            title = ("%s %s" % (title, post.hashtags)).strip()[:2200]
        video_size = len(data)
        # TikTok : chunk 5–64 Mo, sauf fichier < 5 Mo (un seul chunk = taille réelle).
        if video_size < 5 * 1024 * 1024:
            chunk_size = video_size
            total_chunks = 1
        else:
            chunk_size = min(10 * 1024 * 1024, video_size)
            total_chunks = (video_size + chunk_size - 1) // chunk_size
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy,
                "disable_duet": bool(creator.get("duet_disabled")),
                "disable_comment": bool(creator.get("comment_disabled")),
                "disable_stitch": bool(creator.get("stitch_disabled")),
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
        try:
            response = requests.post(
                TIKTOK_VIDEO_INIT_URL,
                headers=self._bearer_headers(token),
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise UserError(_("Init publication TikTok : %s") % exc) from exc
        err = body.get("error") or {}
        if err.get("code") not in ("ok", None, ""):
            raise UserError(
                _("TikTok a refusé l'envoi : %s")
                % (err.get("message") or err.get("code") or response.text[:300])
            )
        info = body.get("data") or {}
        publish_id = info.get("publish_id")
        upload_url = info.get("upload_url")
        if not publish_id or not upload_url:
            raise UserError(_("TikTok n'a pas renvoyé d'URL d'upload."))
        self._put_video_chunks(upload_url, data, chunk_size, mimetype)
        post.sudo().write(
            {
                "tiktok_publish_id": publish_id,
                "tiktok_publish_status": "PROCESSING_UPLOAD",
                "state": "publishing",
            }
        )
        post.message_post(
            body=_(
                "Vidéo envoyée à TikTok (compte %s, confidentialité %s). "
                "Publication asynchrone — suivi du statut en cours."
            )
            % (account.name, privacy)
        )
        return {"ok": True, "pending": True, "publish_id": publish_id}

    def _put_video_chunks(self, upload_url, data, chunk_size, mimetype):
        total = len(data)
        offset = 0
        while offset < total:
            end = min(offset + chunk_size, total)
            chunk = data[offset:end]
            headers = {
                "Content-Type": mimetype or "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": "bytes %s-%s/%s" % (offset, end - 1, total),
            }
            try:
                response = requests.put(
                    upload_url, data=chunk, headers=headers, timeout=120
                )
            except requests.RequestException as exc:
                raise UserError(_("Upload TikTok interrompu : %s") % exc) from exc
            if response.status_code not in (200, 201, 206):
                raise UserError(
                    _("Upload TikTok HTTP %s : %s")
                    % (response.status_code, (response.text or "")[:300])
                )
            offset = end

    def fetch_publish_status(self, post):
        publish_id = (post.tiktok_publish_id or "").strip()
        if not publish_id:
            return {"ok": False, "message": "Pas de publish_id"}
        Account = self.env["doorway.social.account"].sudo()
        accounts = post.account_ids.filtered(lambda a: a.platform == "tiktok")
        if not accounts:
            domain = [("platform", "=", "tiktok"), ("connection_state", "=", "connected")]
            if post.pipeline_id:
                domain.append(("pipeline_id", "=", post.pipeline_id.id))
            accounts = Account.search(domain, limit=1)
        if not accounts:
            return {"ok": False, "message": "Compte TikTok introuvable"}
        token = self.refresh_account_token(accounts[0])
        if not token:
            return {"ok": False, "message": "Token TikTok expiré"}
        try:
            response = requests.post(
                TIKTOK_STATUS_URL,
                headers=self._bearer_headers(token),
                json={"publish_id": publish_id},
                timeout=REQUEST_TIMEOUT,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": str(exc)}
        err = body.get("error") or {}
        if err.get("code") not in ("ok", None, ""):
            return {
                "ok": False,
                "message": err.get("message") or err.get("code") or "status refusé",
            }
        data = body.get("data") or {}
        status = data.get("status") or ""
        post.sudo().write({"tiktok_publish_status": status})
        if status == "PUBLISH_COMPLETE":
            self._mark_published(post, data)
            return {"ok": True, "status": status, "published": True}
        if status in ("FAILED", "PUBLISH_FAILED", "FAILED_TO_PUBLISH"):
            fail_msg = data.get("fail_reason") or "Publication TikTok échouée."
            post.sudo().write({"state": "failed"})
            post.message_post(body=_("TikTok : %s") % fail_msg)
            return {"ok": True, "status": status, "published": False}
        return {"ok": True, "status": status, "published": False}

    def _mark_published(self, post, data):
        now = fields.Datetime.now()
        post.sudo().write(
            {
                "state": "published",
                "published_date": now,
                "tiktok_publish_status": "PUBLISH_COMPLETE",
            }
        )
        extra = ""
        if data.get("publicaly_available_post_id") or data.get("publicly_available_post_id"):
            extra = " ID post TikTok enregistré."
        post.message_post(body=_("TikTok : publication confirmée.%s") % extra)
        if not post.publish_charged:
            credit_api = self.env["doorway.credit.api"]
            cost = credit_api.get_cost("doorway_credits.cost_social_publish", 1.0)
            company = post._credit_company()
            idem = "social_publish:post:%s" % post.id
            res = credit_api.consume(
                company,
                cost,
                "Publication TikTok « %s »" % (post.name or post.id),
                ref="post:%s" % post.id,
                service="social_publish",
                idempotency_key=idem,
            )
            if res.get("success"):
                post.sudo().write({"publish_charged": True})

    @api.model
    def _cron_poll_publish_status(self):
        self.ensure_brand_tiktok_accounts()
        Post = self.env["doorway.social.post"].sudo()
        pending = Post.search(
            [
                ("platform", "=", "tiktok"),
                ("state", "=", "publishing"),
                ("tiktok_publish_id", "!=", False),
            ]
        )
        for post in pending:
            try:
                self.fetch_publish_status(post)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("TikTok poll post %s : %s", post.id, exc)
        return True
