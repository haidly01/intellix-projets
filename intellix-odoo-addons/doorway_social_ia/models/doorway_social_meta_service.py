# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class DoorwaySocialMetaService(models.AbstractModel):
    _name = "doorway.social.meta.service"
    _description = "Service Meta Graph API (Facebook / Instagram)"

    def _get(self, path, token, params=None):
        query = dict(params or {})
        query["access_token"] = token
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/{path.lstrip('/')}",
                params=query,
                timeout=30,
            )
            data = resp.json()
            if resp.status_code >= 400 or data.get("error"):
                err = data.get("error") or {}
                return {"ok": False, "message": err.get("message") or resp.text}
            return {"ok": True, "data": data}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def _post(self, path, token, payload=None):
        data = dict(payload or {})
        data["access_token"] = token
        try:
            resp = requests.post(
                f"{GRAPH_BASE}/{path.lstrip('/')}",
                data=data,
                timeout=45,
            )
            body = resp.json()
            if resp.status_code >= 400 or body.get("error"):
                err = body.get("error") or {}
                return {"ok": False, "message": err.get("message") or resp.text}
            return {"ok": True, "data": body}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def _post_files(self, path, token, payload=None, files=None):
        """POST multipart (upload binaire de photo/vidéo vers Graph API)."""
        data = dict(payload or {})
        data["access_token"] = token
        try:
            resp = requests.post(
                f"{GRAPH_BASE}/{path.lstrip('/')}",
                data=data,
                files=files or None,
                timeout=180,
            )
            body = resp.json()
            if resp.status_code >= 400 or body.get("error"):
                err = body.get("error") or {}
                return {"ok": False, "message": err.get("message") or resp.text}
            return {"ok": True, "data": body}
        except requests.RequestException as exc:
            return {"ok": False, "message": str(exc)}

    def validate_account(self, account):
        token = (account.access_token or "").strip()
        ext_id = (account.external_account_id or "").strip()
        if not token or not ext_id:
            return {"ok": False, "message": _("Token ou ID externe manquant")}
        if account.platform == "instagram":
            res = self._get(
                ext_id,
                token,
                {"fields": "id,username,name"},
            )
        else:
            res = self._get(ext_id, token, {"fields": "id,name"})
        if res["ok"]:
            account.connection_state = "connected"
            data = res["data"]
            if account.platform == "instagram":
                account.name = f"@{data.get('username') or data.get('name') or ext_id}"
            else:
                account.name = data.get("name") or account.name
        else:
            account.connection_state = "expired"
        return res

    def _get_page_pipeline_map(self):
        """Mappe page_id Meta → crm.team selon le routing Lead Ads."""
        pipeline_team_xmlids = {
            "immo": "renovation_conciergerie.crm_team_immobilier",
            "marketing": "renovation_conciergerie.crm_team_marketing",
            "energie": "renovation_conciergerie.crm_team_renovation",
            "haidly": "renovation_conciergerie.crm_team_renovation",
        }
        Team = self.env["crm.team"]
        page_map = {}
        routing = self.env["renovation.meta.leads.routing"]
        global_map = routing.get_global_map() or {}
        for page_id, info in (global_map.get("pages") or {}).items():
            pipeline_key = info.get("pipeline")
            team_xmlid = pipeline_team_xmlids.get(pipeline_key)
            team = (
                self.env.ref(team_xmlid, raise_if_not_found=False)
                if team_xmlid
                else False
            )
            page_map[str(page_id)] = {
                "name": info.get("name") or page_id,
                "pipeline_id": team.id if team else False,
            }
        return page_map

    def _upsert_meta_account(self, Account, platform, external_id, name, token, pipeline_id):
        account = Account.search([
            ("platform", "=", platform),
            ("external_account_id", "=", external_id),
        ], limit=1)
        vals = {
            "name": name,
            "platform": platform,
            "external_account_id": external_id,
            "access_token": token,
            "connection_state": "connected",
            "active": True,
        }
        if pipeline_id:
            vals["pipeline_id"] = pipeline_id
        if account:
            if not account.active:
                return account
            account.write(vals)
            return account
        return Account.create(vals)

    def _fetch_all_meta_pages(self, token):
        """Liste toutes les pages accessibles via Graph API /me/accounts."""
        pages = []
        url = f"{GRAPH_BASE}/me/accounts"
        params = {
            "access_token": token,
            "fields": "id,name,access_token,instagram_business_account{id,username,name}",
            "limit": 50,
        }
        while url:
            try:
                resp = requests.get(url, params=params, timeout=30)
                data = resp.json()
            except requests.RequestException as exc:
                return {"ok": False, "message": str(exc), "pages": []}
            if resp.status_code >= 400 or data.get("error"):
                err = data.get("error") or {}
                return {
                    "ok": False,
                    "message": err.get("message") or resp.text,
                    "pages": [],
                }
            pages.extend(data.get("data") or [])
            next_url = (data.get("paging") or {}).get("next")
            url = next_url
            params = None
        return {"ok": True, "pages": pages}

    def sync_all_meta_pages(self):
        """Importe toutes les pages Meta connues + accessibles via le token Veille."""
        if "doorway.veille.config" not in self.env:
            raise UserError(_("Module Veille Sociale non installé."))
        config = self.env["doorway.veille.config"].search([], limit=1)
        token = (config.meta_access_token or "").strip()
        if not token:
            raise UserError(
                _(
                    "Aucun token Meta dans Veille Sociale → Connexions & sources. "
                    "Collez un token long-lived puis réessayez."
                )
            )

        Account = self.env["doorway.social.account"].sudo()
        page_pipeline = self._get_page_pipeline_map()
        synced = Account.browse()
        errors = []

        fetch = self._fetch_all_meta_pages(token)
        discovered = {}
        if fetch["ok"]:
            for page in fetch["pages"]:
                page_id = str(page.get("id") or "")
                if not page_id:
                    continue
                discovered[page_id] = page
        else:
            errors.append(fetch["message"])

        # Pages documentées (Lead Ads) + pages découvertes via l'API
        all_page_ids = set(page_pipeline) | set(discovered)
        for page_id in sorted(all_page_ids):
            page_data = discovered.get(page_id) or {}
            meta = page_pipeline.get(page_id) or {}
            page_name = page_data.get("name") or meta.get("name") or page_id
            page_token = (page_data.get("access_token") or token).strip()
            pipeline_id = meta.get("pipeline_id")

            fb = self._upsert_meta_account(
                Account,
                "facebook",
                page_id,
                page_name,
                page_token,
                pipeline_id,
            )
            synced |= fb
            res = self.validate_account(fb)
            if not res["ok"]:
                fb.connection_state = "expired"
                if page_id not in discovered:
                    errors.append("%s (FB %s) : page non accessible avec le token actuel" % (
                        page_name, page_id
                    ))

            ig_data = page_data.get("instagram_business_account") or {}
            ig_id = str(ig_data.get("id") or "").strip()
            if ig_id:
                ig_name = ig_data.get("username") or ig_data.get("name") or ig_id
                if ig_data.get("username"):
                    ig_name = "@%s" % ig_data["username"]
                ig = self._upsert_meta_account(
                    Account,
                    "instagram",
                    ig_id,
                    ig_name,
                    page_token,
                    pipeline_id,
                )
                synced |= ig
                res = self.validate_account(ig)
                if not res["ok"]:
                    ig.connection_state = "expired"

        # Fallback Veille : page/IG principale si aucune page API
        if not discovered and config.facebook_page_id:
            synced |= self.sync_from_veille_config()

        self.env["ir.config_parameter"].sudo().set_param(
            "doorway_social_ia.meta_system_user_token", token
        )

        if not synced:
            raise UserError(
                _("Aucun compte Meta créé. %s")
                % (errors[0] if errors else _("Vérifiez le token Veille."))
            )
        return synced

    def sync_from_veille_config(self):
        """Importe FB + IG depuis doorway.veille.config si disponible."""
        if "doorway.veille.config" not in self.env:
            raise UserError(_("Module Veille Sociale non installé."))
        Config = self.env["doorway.veille.config"]
        config = Config.search([], limit=1)
        if not config or not (config.meta_access_token or "").strip():
            raise UserError(_("Aucun token Meta dans la configuration Veille."))

        token = config.meta_access_token.strip()
        Account = self.env["doorway.social.account"].sudo()
        created = Account.browse()
        page_pipeline = self._get_page_pipeline_map()
        pipeline_id = (
            page_pipeline.get(str(config.facebook_page_id or ""), {}).get("pipeline_id")
        )

        if config.facebook_page_id:
            fb = Account.search([
                ("platform", "=", "facebook"),
                ("external_account_id", "=", config.facebook_page_id),
            ], limit=1)
            vals = {
                "name": config.meta_facebook_name or "Facebook",
                "platform": "facebook",
                "external_account_id": config.facebook_page_id,
                "access_token": token,
                "connection_state": "connected",
            }
            if pipeline_id:
                vals["pipeline_id"] = pipeline_id
            if fb:
                fb.write(vals)
                created |= fb
            else:
                fb = Account.create(vals)
                created |= fb
            if not self.validate_account(fb)["ok"]:
                fb.connection_state = "expired"

        ig_id = (config.instagram_account_id or "").strip()
        if ig_id:
            ig = Account.search([
                ("platform", "=", "instagram"),
                ("external_account_id", "=", ig_id),
            ], limit=1)
            vals = {
                "name": config.meta_instagram_username
                and f"@{config.meta_instagram_username}"
                or "Instagram",
                "platform": "instagram",
                "external_account_id": ig_id,
                "access_token": token,
                "connection_state": "connected",
            }
            if pipeline_id:
                vals["pipeline_id"] = pipeline_id
            if ig:
                ig.write(vals)
                created |= ig
            else:
                ig = Account.create(vals)
                created |= ig
            if not self.validate_account(ig)["ok"]:
                ig.connection_state = "expired"

        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("doorway_social_ia.meta_system_user_token", token)

        return created

    def publish_post(self, post):
        account = post.account_ids.filtered(
            lambda a: a.platform == post.platform and a.connection_state == "connected"
        )[:1]
        if not account:
            account = self.env["doorway.social.account"].search([
                ("platform", "=", post.platform),
                ("connection_state", "=", "connected"),
            ], limit=1)
        if not account:
            raise UserError(
                _("Aucun compte %s connecté — synchronisez depuis Veille ou connectez manuellement.")
                % post.platform
            )

        token = account.access_token
        caption = self._build_caption(post)

        if post.platform == "facebook":
            return self._publish_facebook_page(account, post, token, caption)
        if post.platform == "instagram":
            return self._publish_instagram(account, post, token, caption)
        raise UserError(_("Plateforme Meta non supportée : %s") % post.platform)

    def _build_caption(self, post):
        parts = [post.caption or post.hook or ""]
        if post.hashtags:
            parts.append(post.hashtags)
        return "\n\n".join(p for p in parts if p).strip()

    def _fb_privacy(self, post):
        """Mappe la confidentialité du post vers le paramètre Graph API."""
        if getattr(post, "privacy", "public") == "limited":
            return json.dumps({"value": "ALL_FRIENDS"})
        return json.dumps({"value": "EVERYONE"})

    def _upload_fb_photo(self, page_id, token, media, message=None, published=True, privacy=None):
        """Upload d'une photo (binaire si attachment, sinon par URL)."""
        payload = {"published": "true" if published else "false"}
        if message:
            payload["message"] = message
        if privacy and published:
            payload["privacy"] = privacy
        att = media.get("attachment")
        if att:
            files = {
                "source": (
                    att.name or "photo",
                    att.raw or b"",
                    media.get("mimetype") or "image/jpeg",
                )
            }
            return self._post_files(f"{page_id}/photos", token, payload, files)
        payload["url"] = media.get("public_url")
        return self._post(f"{page_id}/photos", token, payload)

    def _publish_fb_video(self, page_id, token, caption, media, privacy=None):
        payload = {"description": caption or ""}
        if privacy:
            payload["privacy"] = privacy
        att = media.get("attachment")
        if att:
            files = {
                "source": (
                    att.name or "video.mp4",
                    att.raw or b"",
                    media.get("mimetype") or "video/mp4",
                )
            }
            return self._post_files(f"{page_id}/videos", token, payload, files)
        payload["file_url"] = media.get("public_url")
        return self._post(f"{page_id}/videos", token, payload)

    def _publish_facebook_page(self, account, post, token, caption):
        page_id = account.external_account_id
        media = post._collect_media()
        images = [m for m in media if not m["is_video"]]
        videos = [m for m in media if m["is_video"]]
        privacy = self._fb_privacy(post)

        # 1) Vidéo (reel / publication vidéo) → endpoint /videos
        if videos:
            res = self._publish_fb_video(page_id, token, caption, videos[0], privacy)
            if not res["ok"]:
                raise UserError(_("Facebook (vidéo) : %s") % res["message"])
            post.message_post(
                body=_("Vidéo publiée sur Facebook — ID %s") % res["data"].get("id", "?")
            )
            return res["data"]

        # 2) Aucune image → texte (+ lien éventuel)
        if not images:
            payload = {"message": caption, "privacy": privacy}
            if post.image_url:
                payload["link"] = post.image_url
            res = self._post(f"{page_id}/feed", token, payload)
            if not res["ok"]:
                raise UserError(_("Facebook : %s") % res["message"])
            post.message_post(
                body=_("Publié sur Facebook — ID %s") % res["data"].get("id", "?")
            )
            return res["data"]

        # 3) Photo unique → /photos directement publié
        if len(images) == 1:
            res = self._upload_fb_photo(
                page_id, token, images[0], message=caption, published=True, privacy=privacy
            )
            if not res["ok"]:
                raise UserError(_("Facebook (photo) : %s") % res["message"])
            post.message_post(
                body=_("Photo publiée sur Facebook — ID %s")
                % (res["data"].get("post_id") or res["data"].get("id", "?"))
            )
            return res["data"]

        # 4) Plusieurs photos → upload non publié + post feed avec attached_media
        media_fbids = []
        for img in images:
            up = self._upload_fb_photo(page_id, token, img, published=False)
            if not up["ok"]:
                raise UserError(_("Facebook (photo) : %s") % up["message"])
            media_fbids.append(up["data"].get("id"))
        payload = {"message": caption, "privacy": privacy}
        for i, fbid in enumerate(media_fbids):
            payload["attached_media[%d]" % i] = json.dumps({"media_fbid": fbid})
        res = self._post(f"{page_id}/feed", token, payload)
        if not res["ok"]:
            raise UserError(_("Facebook (carrousel) : %s") % res["message"])
        post.message_post(
            body=_("Carrousel publié sur Facebook — ID %s") % res["data"].get("id", "?")
        )
        return res["data"]

    def _ig_create_container(self, ig_id, token, params):
        res = self._post(f"{ig_id}/media", token, params)
        if not res["ok"]:
            raise UserError(_("Instagram (conteneur) : %s") % res["message"])
        return res["data"].get("id")

    def _ig_publish_container(self, ig_id, token, creation_id, post):
        publish_res = self._post(
            f"{ig_id}/media_publish", token, {"creation_id": creation_id}
        )
        if not publish_res["ok"]:
            raise UserError(_("Instagram publish : %s") % publish_res["message"])
        post.message_post(
            body=_("Publié sur Instagram — ID %s") % publish_res["data"].get("id", "?")
        )
        return publish_res["data"]

    def _publish_instagram(self, account, post, token, caption):
        ig_id = account.external_account_id
        media = post._collect_media()
        images = [m for m in media if not m["is_video"]]
        videos = [m for m in media if m["is_video"]]

        if not images and not videos:
            raise UserError(
                _(
                    "Instagram requiert au moins une image ou vidéo. "
                    "Ajoutez un média dans le composer."
                )
            )

        # Instagram nécessite des URLs publiques (les serveurs Meta téléchargent
        # le média). Les attachments uploadés exposent une URL /web/content signée.
        # Vidéo / Reel
        if videos:
            video_url = videos[0]["public_url"]
            if not video_url:
                raise UserError(
                    _("La vidéo Instagram doit être accessible via une URL publique.")
                )
            params = {
                "caption": caption,
                "media_type": "REELS" if post.post_format == "reel" else "VIDEO",
                "video_url": video_url,
            }
            creation_id = self._ig_create_container(ig_id, token, params)
            return self._ig_publish_container(ig_id, token, creation_id, post)

        # Photo unique
        if len(images) == 1:
            image_url = images[0]["public_url"]
            if not image_url:
                raise UserError(
                    _("L'image Instagram doit être accessible via une URL publique.")
                )
            creation_id = self._ig_create_container(
                ig_id, token, {"caption": caption, "image_url": image_url}
            )
            return self._ig_publish_container(ig_id, token, creation_id, post)

        # Carrousel (2 à 10 images)
        child_ids = []
        for img in images[:10]:
            if not img["public_url"]:
                continue
            child = self._ig_create_container(
                ig_id,
                token,
                {"image_url": img["public_url"], "is_carousel_item": "true"},
            )
            child_ids.append(child)
        if not child_ids:
            raise UserError(_("Aucune image Instagram exploitable (URL publique manquante)."))
        creation_id = self._ig_create_container(
            ig_id,
            token,
            {
                "caption": caption,
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
            },
        )
        return self._ig_publish_container(ig_id, token, creation_id, post)

    def _parse_fb_datetime(self, iso):
        from datetime import datetime, timezone

        from odoo import fields

        if not iso:
            return fields.Datetime.now()
        try:
            normalized = str(iso).replace("+0000", "+00:00").replace("Z", "+00:00")
            if "T" in normalized:
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            return fields.Datetime.to_datetime(normalized)
        except (TypeError, ValueError):
            return fields.Datetime.now()

    def _import_messenger_thread(self, account, thread):
        """Importe une conversation Messenger (page Facebook) dans l'inbox."""
        from odoo import fields

        Inbox = self.env["doorway.social.inbox"].sudo()
        Message = self.env["doorway.social.message"].sudo()
        page_id = str(account.external_account_id)
        participants = (thread.get("participants") or {}).get("data") or []
        user = next(
            (p for p in participants if str(p.get("id")) != page_id),
            None,
        )
        if not user:
            return 0

        external_id = str(user.get("id"))
        contact_name = (
            user.get("name")
            or (user.get("email") or "").split("@")[0]
            or external_id
        )
        messages_data = list(
            reversed((thread.get("messages") or {}).get("data") or [])
        )
        if not messages_data:
            return 0

        channel = Inbox.search(
            [
                ("inbox_source", "=", "messenger"),
                ("account_id", "=", account.id),
                ("external_id", "=", external_id),
            ],
            limit=1,
        )
        newest = messages_data[-1]
        preview = (newest.get("message") or "")[:500]
        last_dt = self._parse_fb_datetime(newest.get("created_time"))
        if not channel:
            channel = Inbox.create(
                {
                    "name": "Messenger — %s" % contact_name,
                    "inbox_source": "messenger",
                    "external_id": external_id,
                    "external_name": contact_name,
                    "account_id": account.id,
                    "state": "read",
                    "unread_count": 0,
                    "last_message": preview,
                    "last_message_date": last_dt,
                }
            )
        else:
            channel.write(
                {
                    "external_name": contact_name,
                    "last_message": preview or channel.last_message,
                    "last_message_date": last_dt,
                }
            )

        imported = 0
        for msg in messages_data:
            ext_id = msg.get("id")
            if ext_id and Message.search(
                [("external_msg_id", "=", ext_id)], limit=1
            ):
                continue
            from_id = str((msg.get("from") or {}).get("id") or "")
            content = (msg.get("message") or "").strip()
            if not content:
                continue
            direction = "outbound" if from_id == page_id else "inbound"
            Message.create(
                {
                    "conversation_id": channel.id,
                    "direction": direction,
                    "content": content,
                    "external_msg_id": ext_id,
                    "is_read": True,
                }
            )
            imported += 1
        return imported

    def _get_or_create_comment_bucket(self, account):
        Inbox = self.env["doorway.social.inbox"].sudo()
        ext_id = "comments:%s" % account.id
        inbox_source = (
            "instagram" if account.platform == "instagram" else "messenger"
        )
        channel = Inbox.search(
            [
                ("external_id", "=", ext_id),
                ("account_id", "=", account.id),
            ],
            limit=1,
        )
        if channel:
            return channel
        return Inbox.create(
            {
                "name": "%s — Commentaires" % account.name,
                "inbox_source": inbox_source,
                "external_id": ext_id,
                "external_name": "Commentaires",
                "account_id": account.id,
                "state": "read",
                "unread_count": 0,
            }
        )

    def _import_fb_post_comments(self, account, stats):
        Comment = self.env["doorway.social.comment"].sudo()
        token = account.access_token
        page_id = account.external_account_id
        res = self._get(
            "%s/feed" % page_id,
            token,
            {
                "fields": "id,message,permalink_url,comments.limit(50){id,from,message,created_time}",
                "limit": 25,
            },
        )
        if not res["ok"]:
            stats["errors"].append("%s (commentaires) : %s" % (
                account.name, res["message"]
            ))
            return 0

        bucket = self._get_or_create_comment_bucket(account)
        imported = 0
        latest_preview = ""
        latest_dt = False
        for post in res["data"].get("data") or []:
            post_preview = (post.get("message") or "")[:120]
            post_url = post.get("permalink_url") or ""
            for comment in (post.get("comments") or {}).get("data") or []:
                ext_id = comment.get("id")
                if ext_id and Comment.search(
                    [("external_comment_id", "=", ext_id)], limit=1
                ):
                    continue
                from_user = comment.get("from") or {}
                content = (comment.get("message") or "").strip()
                if not content:
                    continue
                created = self._parse_fb_datetime(comment.get("created_time"))
                Comment.create(
                    {
                        "conversation_id": bucket.id,
                        "author_name": from_user.get("name") or "",
                        "author_id_ext": str(from_user.get("id") or ""),
                        "content": content,
                        "post_preview": post_preview,
                        "post_url": post_url,
                        "platform": "facebook",
                        "external_comment_id": ext_id,
                    }
                )
                imported += 1
                if not latest_dt or created > latest_dt:
                    latest_dt = created
                    latest_preview = content[:500]

        if imported:
            bucket.write(
                {
                    "last_message": latest_preview,
                    "last_message_date": latest_dt,
                }
            )
            bucket._refresh_comment_flags()
        return imported

    def _import_ig_media_comments(self, account, stats):
        Comment = self.env["doorway.social.comment"].sudo()
        res = self._get(
            "%s/media" % account.external_account_id,
            account.access_token,
            {
                "fields": "id,caption,permalink,comments{text,username,timestamp,id}",
                "limit": 25,
            },
        )
        if not res["ok"]:
            stats["errors"].append("%s (IG commentaires) : %s" % (
                account.name, res["message"]
            ))
            return 0

        bucket = self._get_or_create_comment_bucket(account)
        imported = 0
        latest_preview = ""
        latest_dt = False
        for media in res["data"].get("data") or []:
            post_preview = (media.get("caption") or "")[:120]
            post_url = media.get("permalink") or ""
            for comment in (media.get("comments") or {}).get("data") or []:
                ext_id = comment.get("id")
                if ext_id and Comment.search(
                    [("external_comment_id", "=", ext_id)], limit=1
                ):
                    continue
                content = (comment.get("text") or "").strip()
                if not content:
                    continue
                created = self._parse_fb_datetime(comment.get("timestamp"))
                Comment.create(
                    {
                        "conversation_id": bucket.id,
                        "author_name": comment.get("username") or "",
                        "content": content,
                        "post_preview": post_preview,
                        "post_url": post_url,
                        "platform": "instagram",
                        "external_comment_id": ext_id,
                    }
                )
                imported += 1
                if not latest_dt or created > latest_dt:
                    latest_dt = created
                    latest_preview = content[:500]

        if imported:
            bucket.write(
                {
                    "last_message": latest_preview,
                    "last_message_date": latest_dt,
                }
            )
            bucket._refresh_comment_flags()
        return imported

    def sync_meta_comments(self, stats=None):
        """Importe les commentaires FB/IG (nécessite pages_read_engagement / IG comments)."""
        stats = stats or {"threads": 0, "messages": 0, "comments": 0, "errors": []}
        Account = self.env["doorway.social.account"].sudo()
        for account in Account.search(
            [
                ("active", "=", True),
                ("connection_state", "=", "connected"),
                ("platform", "=", "facebook"),
                ("access_token", "!=", False),
            ]
        ):
            stats["comments"] += self._import_fb_post_comments(account, stats)
        for account in Account.search(
            [
                ("active", "=", True),
                ("connection_state", "=", "connected"),
                ("platform", "=", "instagram"),
                ("access_token", "!=", False),
            ]
        ):
            stats["comments"] += self._import_ig_media_comments(account, stats)
        return stats

    def sync_meta_inbox(self):
        """Synchronise conversations Messenger + commentaires depuis Meta Graph API."""
        stats = {"threads": 0, "messages": 0, "comments": 0, "errors": []}
        Account = self.env["doorway.social.account"].sudo()
        accounts = Account.search(
            [
                ("active", "=", True),
                ("connection_state", "=", "connected"),
                ("platform", "=", "facebook"),
                ("access_token", "!=", False),
            ]
        )
        for account in accounts:
            res = self._get(
                "%s/conversations" % account.external_account_id,
                account.access_token,
                {
                    "platform": "messenger",
                    "fields": "id,participants,updated_time,messages.limit(50){message,from,created_time,id}",
                    "limit": 100,
                },
            )
            if not res["ok"]:
                stats["errors"].append("%s : %s" % (account.name, res["message"]))
                continue
            threads = res["data"].get("data") or []
            stats["threads"] += len(threads)
            for thread in threads:
                stats["messages"] += self._import_messenger_thread(account, thread)

        self.sync_meta_comments(stats)
        _logger.info(
            "Meta inbox sync: %s threads, %s messages, %s comments, %s errors",
            stats["threads"],
            stats["messages"],
            stats["comments"],
            len(stats["errors"]),
        )
        return stats

    def cron_sync_meta_inbox(self):
        self.sync_meta_inbox()

    def send_whatsapp(self, phone_number_id, to, text, token=None):
        token = token or self.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.meta_system_user_token"
        )
        if not token:
            return False
        res = self._post(
            f"{phone_number_id}/messages",
            token,
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
        )
        return res["ok"]
