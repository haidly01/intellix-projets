# -*- coding: utf-8 -*-
"""Validation Meta Graph API (page Facebook + compte Instagram)."""
import logging

import requests

_logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = "https://graph.facebook.com/%s" % GRAPH_API_VERSION
REQUEST_TIMEOUT = 25


class MetaGraphService:
    """Vérifie token, page Facebook et compte Instagram configurés dans Odoo."""

    def __init__(self, env):
        self.env = env

    def _get(self, path, token, params=None):
        query = dict(params or {})
        query["access_token"] = token
        url = "%s/%s" % (GRAPH_BASE, path.lstrip("/"))
        try:
            response = requests.get(url, params=query, timeout=REQUEST_TIMEOUT)
            data = response.json()
            if response.status_code >= 400 or "error" in data:
                err = data.get("error") or {}
                message = err.get("message") or response.text or "Erreur Graph API"
                return {"ok": False, "message": message, "data": data}
            return {"ok": True, "data": data}
        except requests.RequestException as exc:
            _logger.warning("Meta Graph API: %s", exc)
            return {"ok": False, "message": str(exc), "data": {}}

    def validate_config(self, config):
        """
        Valide page FB, compte IG et token.
        Renvoie un dict pour mise à jour de doorway.veille.config.
        """
        token = (config.meta_access_token or "").strip()
        page_id = (config.facebook_page_id or "").strip()
        ig_id = (config.instagram_account_id or "").strip()

        result = {
            "facebook_ok": False,
            "instagram_ok": False,
            "facebook_name": False,
            "instagram_username": False,
            "messages": [],
        }

        if not token:
            result["messages"].append("Token Meta manquant.")
            return result

        page_linked_ig = {}

        if page_id:
            page = self._get(
                page_id,
                token,
                {
                    "fields": (
                        "id,name,instagram_business_account{id,username},"
                        "connected_instagram_account{id,username}"
                    )
                },
            )
            if page["ok"]:
                pdata = page["data"]
                result["facebook_ok"] = True
                result["facebook_name"] = pdata.get("name") or page_id
                result["messages"].append(
                    "Facebook : page « %s » (ID %s) accessible."
                    % (result["facebook_name"], pdata.get("id", page_id))
                )
                page_linked_ig = (
                    pdata.get("instagram_business_account")
                    or pdata.get("connected_instagram_account")
                    or {}
                )
                if page_linked_ig.get("id"):
                    linked = page_linked_ig
                    result["messages"].append(
                        "Instagram lié à la page : @%s (ID %s)."
                        % (linked.get("username") or "?", linked.get("id"))
                    )
                    if ig_id and str(linked.get("id")) != str(ig_id):
                        result["messages"].append(
                            "Conseil : mettez à jour l'ID Instagram Odoo avec %s."
                            % linked.get("id")
                        )
            else:
                result["messages"].append("Facebook : %s" % page["message"])
        else:
            result["messages"].append("ID page Facebook non renseigné.")

        ig_candidates = []
        if page_linked_ig.get("id"):
            ig_candidates.append(page_linked_ig)
        if ig_id:
            ig_candidates.append({"id": ig_id})

        seen = set()
        for candidate in ig_candidates:
            cid = str(candidate.get("id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            ig = self._get(cid, token, {"fields": "id,username,name"})
            if ig["ok"]:
                idata = ig["data"]
                result["instagram_ok"] = True
                result["instagram_username"] = (
                    idata.get("username") or idata.get("name") or cid
                )
                result["messages"].append(
                    "Instagram : @%s (ID %s) accessible via Graph API."
                    % (result["instagram_username"], idata.get("id", cid))
                )
                break
            err = ig.get("message") or ""
            if candidate is page_linked_ig or cid == str(ig_id):
                result["messages"].append("Instagram (ID %s) : %s" % (cid, err))

        if ig_id and not result["instagram_ok"]:
            result["messages"].append(
                "Instagram : l'ID %s n'est pas reconnu par Graph API "
                "(utilisez l'ID « Instagram Business » depuis Meta Business Suite, "
                "onglet Comptes Instagram liés à la page). n8n peut quand même "
                "fonctionner si le workflow utilise le bon identifiant."
                % ig_id
            )
            # Token + page OK : on garde la collecte n8n active malgré l'échec API direct
            if result["facebook_ok"] and ig_id:
                result["instagram_ok"] = True
                result["instagram_username"] = result["instagram_username"] or (
                    "ID %s (non vérifié API)" % ig_id
                )

        if not ig_id:
            result["messages"].append("ID compte Instagram non renseigné.")

        return result

    def _post(self, path, token, data=None):
        query = dict(data or {})
        query["access_token"] = token
        url = "%s/%s" % (GRAPH_BASE, path.lstrip("/"))
        try:
            response = requests.post(url, data=query, timeout=REQUEST_TIMEOUT)
            body = response.json()
            if response.status_code >= 400 or "error" in body:
                err = body.get("error") or {}
                message = err.get("message") or response.text or "Erreur Graph API"
                return {"ok": False, "message": message, "data": body}
            return {"ok": True, "data": body}
        except requests.RequestException as exc:
            _logger.warning("Meta Graph API POST: %s", exc)
            return {"ok": False, "message": str(exc), "data": {}}

    def fetch_conversation(self, config, signal):
        """Récupère les commentaires / réponses liés au signal."""
        token = (config.meta_access_token or "").strip()
        if not token:
            return {"ok": False, "message": "Token Meta manquant.", "messages": []}

        object_id = signal._get_external_object_id()
        if not object_id:
            return {
                "ok": False,
                "message": "ID post/commentaire Meta manquant sur ce signal.",
                "messages": [],
            }

        if signal.source == "facebook":
            return self._fetch_facebook_thread(token, object_id, signal.external_comment_id)
        if signal.source == "instagram":
            return self._fetch_instagram_thread(token, object_id, signal.external_comment_id)
        return {"ok": False, "message": "Source non Meta.", "messages": []}

    def _fetch_facebook_thread(self, token, object_id, comment_id=None):
        messages = []
        if comment_id:
            parent = self._get(
                comment_id,
                token,
                {"fields": "id,message,from,created_time,parent"},
            )
            if parent["ok"]:
                messages.append(self._normalize_fb_comment(parent["data"], "facebook"))

        comments = self._get(
            object_id,
            token,
            {
                "fields": "comments.limit(50){id,message,from,created_time,comments.limit(25){id,message,from,created_time}}",
            },
        )
        if not comments["ok"]:
            if messages:
                return {"ok": True, "messages": messages}
            return {"ok": False, "message": comments["message"], "messages": []}

        data = comments["data"]
        thread = (data.get("comments") or {}).get("data") or []
        for item in thread:
            messages.append(self._normalize_fb_comment(item, "facebook"))
            for reply in (item.get("comments") or {}).get("data") or []:
                messages.append(self._normalize_fb_comment(reply, "facebook"))

        if not messages and data.get("message"):
            messages.append(
                {
                    "external_id": data.get("id") or object_id,
                    "author_name": (data.get("from") or {}).get("name") or "Facebook",
                    "body": data.get("message") or "",
                    "posted_at": data.get("created_time"),
                    "direction": "inbound",
                    "platform": "facebook",
                }
            )
        return {"ok": True, "messages": self._dedupe_messages(messages)}

    def _fetch_instagram_thread(self, token, media_id, comment_id=None):
        messages = []
        if comment_id:
            parent = self._get(
                comment_id,
                token,
                {"fields": "id,text,username,timestamp,replies{id,text,username,timestamp}"},
            )
            if parent["ok"]:
                pdata = parent["data"]
                messages.append(self._normalize_ig_comment(pdata))
                for reply in (pdata.get("replies") or {}).get("data") or []:
                    messages.append(self._normalize_ig_comment(reply, direction="outbound"))

        comments = self._get(
            media_id,
            token,
            {"fields": "comments.limit(50){id,text,username,timestamp,replies{id,text,username,timestamp}}"},
        )
        if not comments["ok"]:
            if messages:
                return {"ok": True, "messages": messages}
            return {"ok": False, "message": comments["message"], "messages": []}

        for item in (comments["data"].get("comments") or {}).get("data") or []:
            messages.append(self._normalize_ig_comment(item))
            for reply in (item.get("replies") or {}).get("data") or []:
                messages.append(self._normalize_ig_comment(reply, direction="outbound"))

        return {"ok": True, "messages": self._dedupe_messages(messages)}

    @staticmethod
    def _normalize_fb_comment(data, platform="facebook", direction="inbound"):
        return {
            "external_id": data.get("id"),
            "author_name": (data.get("from") or {}).get("name") or "Facebook",
            "body": data.get("message") or "",
            "posted_at": data.get("created_time"),
            "direction": direction,
            "platform": platform,
        }

    @staticmethod
    def _normalize_ig_comment(data, direction="inbound"):
        return {
            "external_id": data.get("id"),
            "author_name": data.get("username") or "Instagram",
            "body": data.get("text") or "",
            "posted_at": data.get("timestamp"),
            "direction": direction,
            "platform": "instagram",
        }

    @staticmethod
    def _dedupe_messages(messages):
        seen = set()
        unique = []
        for msg in messages:
            key = msg.get("external_id") or (msg.get("author_name"), msg.get("body"))
            if key in seen:
                continue
            seen.add(key)
            if msg.get("body"):
                unique.append(msg)
        return unique

    def send_reply(self, config, signal, message_text):
        """Publie une réponse sur Facebook ou Instagram."""
        token = (config.meta_access_token or "").strip()
        text = (message_text or "").strip()
        if not token:
            return {"ok": False, "message": "Token Meta manquant."}
        if not text:
            return {"ok": False, "message": "Message vide."}

        target_id = signal._get_reply_target_id()
        if not target_id:
            return {
                "ok": False,
                "message": "Impossible de déterminer le commentaire cible. "
                "Synchronisez la conversation d'abord.",
            }

        if signal.source == "facebook":
            result = self._post(
                "%s/comments" % target_id,
                token,
                {"message": text},
            )
        elif signal.source == "instagram":
            media_id = signal._get_external_object_id()
            if media_id and target_id == media_id:
                result = self._post(
                    "%s/comments" % target_id,
                    token,
                    {"message": text},
                )
            else:
                result = self._post(
                    "%s/replies" % target_id,
                    token,
                    {"message": text},
                )
        else:
            return {"ok": False, "message": "Réponse API disponible pour Facebook/Instagram seulement."}

        if not result["ok"]:
            return result
        reply_id = (result.get("data") or {}).get("id")
        return {
            "ok": True,
            "message": "Réponse publiée.",
            "external_id": reply_id,
            "body": text,
        }

    def like_object(self, config, signal):
        """Like un post ou commentaire Meta (réactivation douce)."""
        token = (config.meta_access_token or "").strip()
        if not token:
            return {"ok": False, "message": "Token Meta manquant."}

        target_id = signal._get_reply_target_id() or signal._get_external_object_id()
        if not target_id:
            return {
                "ok": False,
                "message": "Impossible de déterminer la cible Meta.",
            }

        result = self._post("%s/likes" % target_id, token, {})
        if not result.get("ok"):
            return result
        return {"ok": True, "message": "Like Meta publié.", "external_id": target_id}

