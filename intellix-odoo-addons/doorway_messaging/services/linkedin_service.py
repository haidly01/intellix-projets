# -*- coding: utf-8 -*-
"""LinkedIn API v2 — posts UGC."""
import logging

import requests

_logger = logging.getLogger(__name__)


class LinkedInService:
    def __init__(self, access_token, org_id=None, person_id=None):
        self.access_token = access_token
        self.org_id = org_id
        self.person_id = person_id
        self.base_url = "https://api.linkedin.com/v2"
        self.headers = {
            "Authorization": "Bearer %s" % access_token,
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def publier_post_entreprise(self, texte, image_url=None):
        if not self.org_id:
            return {"success": False, "error": "Organization ID manquant"}
        author = "urn:li:organization:%s" % self.org_id
        return self._publish_ugc(author, texte, image_url)

    def publier_post_personnel(self, texte, image_url=None):
        if not self.person_id:
            return {"success": False, "error": "Person ID manquant"}
        author = "urn:li:person:%s" % self.person_id
        return self._publish_ugc(author, texte, image_url)

    def _publish_ugc(self, author, texte, image_url=None):
        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": texte},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        if image_url:
            asset_urn = self._upload_image(image_url, author)
            if asset_urn:
                payload["specificContent"]["com.linkedin.ugc.ShareContent"][
                    "shareMediaCategory"
                ] = "IMAGE"
                payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                    {
                        "status": "READY",
                        "description": {"text": ""},
                        "media": asset_urn,
                        "title": {"text": ""},
                    }
                ]
        try:
            response = requests.post(
                "%s/ugcPosts" % self.base_url,
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "")
                return {"success": True, "post_id": post_id}
            return {"success": False, "error": response.text}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def _upload_image(self, image_url, author):
        try:
            register_payload = {
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": author,
                    "serviceRelationships": [
                        {
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }
                    ],
                }
            }
            r = requests.post(
                "%s/assets?action=registerUpload" % self.base_url,
                headers=self.headers,
                json=register_payload,
                timeout=15,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            upload_url = data["value"]["uploadMechanism"][
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
            ]["uploadUrl"]
            asset_urn = data["value"]["asset"]
            img_data = requests.get(image_url, timeout=15).content
            requests.put(
                upload_url,
                data=img_data,
                headers={"Authorization": "Bearer %s" % self.access_token},
                timeout=30,
            )
            return asset_urn
        except Exception as exc:  # noqa: BLE001
            _logger.warning("LinkedIn image upload: %s", exc)
            return None

    def get_organization_info(self):
        if not self.org_id:
            return None
        try:
            r = requests.get(
                "%s/organizations/%s" % (self.base_url, self.org_id),
                headers=self.headers,
                timeout=15,
            )
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def get_me(self):
        try:
            r = requests.get(
                "%s/me" % self.base_url, headers=self.headers, timeout=15
            )
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def lister_posts_recents(self, limit=10):
        """Posts UGC récents de l'auteur (organisation ou personne)."""
        author = None
        if self.org_id:
            author = "urn:li:organization:%s" % self.org_id
        elif self.person_id:
            author = "urn:li:person:%s" % self.person_id
        if not author:
            return []
        try:
            r = requests.get(
                "%s/ugcPosts" % self.base_url,
                headers=self.headers,
                params={
                    "q": "authors",
                    "authors": "List(%s)" % author,
                    "count": limit,
                },
                timeout=15,
            )
            if r.status_code != 200:
                _logger.warning("LinkedIn list posts: %s", r.text[:200])
                return []
            elements = r.json().get("elements", [])
            posts = []
            for el in elements:
                text = (
                    el.get("specificContent", {})
                    .get("com.linkedin.ugc.ShareContent", {})
                    .get("shareCommentary", {})
                    .get("text", "")
                )
                posts.append(
                    {
                        "id": el.get("id") or "",
                        "urn": el.get("id") or "",
                        "text": text,
                        "commentary": text,
                    }
                )
            return posts
        except Exception as exc:  # noqa: BLE001
            _logger.warning("LinkedIn list posts: %s", exc)
            return []

    def lister_commentaires(self, post_urn):
        """Commentaires sur un post (nécessite les droits API LinkedIn)."""
        if not post_urn:
            return []
        try:
            r = requests.get(
                "%s/socialActions/%s/comments" % (self.base_url, post_urn),
                headers=self.headers,
                timeout=15,
            )
            if r.status_code != 200:
                return []
            return r.json().get("elements", [])
        except Exception as exc:  # noqa: BLE001
            _logger.warning("LinkedIn comments %s: %s", post_urn, exc)
            return []

    def refresh_access_token(self, client_id, client_secret, refresh_token):
        try:
            r = requests.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "access_token": data["access_token"],
                    "expires_in": data.get("expires_in", 3600),
                    "refresh_token": data.get("refresh_token", refresh_token),
                }
        except Exception as exc:  # noqa: BLE001
            _logger.error("LinkedIn refresh: %s", exc)
        return None
