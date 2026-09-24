# -*- coding: utf-8 -*-
"""Google My Business API v4."""
import logging

import requests

_logger = logging.getLogger(__name__)


class GMBService:
    BASE_URL = "https://mybusiness.googleapis.com/v4"

    def __init__(self, access_token, account_id, location_id):
        self.access_token = access_token
        self.account_id = account_id
        self.location_id = location_id
        self.headers = {
            "Authorization": "Bearer %s" % access_token,
            "Content-Type": "application/json",
        }

    def _location_path(self):
        return "%s/accounts/%s/locations/%s" % (
            self.BASE_URL,
            self.account_id,
            self.location_id,
        )

    def creer_post(
        self,
        texte,
        type_post="STANDARD",
        titre_offre=None,
        date_debut=None,
        date_fin=None,
        image_url=None,
        url_cta=None,
        type_cta="LEARN_MORE",
    ):
        payload = {
            "languageCode": "fr",
            "summary": texte,
            "topicType": type_post,
        }
        if url_cta:
            payload["callToAction"] = {"actionType": type_cta, "url": url_cta}
        if image_url:
            payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": image_url}]
        if type_post == "EVENT" and titre_offre:
            payload["event"] = {
                "title": titre_offre,
                "schedule": {"startDate": date_debut, "endDate": date_fin},
            }
        elif type_post == "OFFER" and titre_offre:
            payload["offer"] = {
                "couponCode": titre_offre,
                "redeemOnlineUrl": url_cta or "",
            }
        try:
            url = "%s/localPosts" % self._location_path()
            r = requests.post(url, headers=self.headers, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                return {
                    "success": True,
                    "post_name": data.get("name"),
                    "post_url": data.get("searchUrl"),
                }
            return {"success": False, "error": r.text}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def lister_posts(self, max_results=20):
        try:
            url = "%s/localPosts" % self._location_path()
            r = requests.get(
                url,
                headers=self.headers,
                params={"pageSize": max_results},
                timeout=15,
            )
            return r.json().get("localPosts", []) if r.status_code == 200 else []
        except Exception as exc:  # noqa: BLE001
            _logger.error("GMB list posts: %s", exc)
            return []

    def lister_avis(self, max_results=50):
        try:
            url = "%s/reviews" % self._location_path()
            r = requests.get(
                url,
                headers=self.headers,
                params={"pageSize": max_results},
                timeout=15,
            )
            return r.json().get("reviews", []) if r.status_code == 200 else []
        except Exception as exc:  # noqa: BLE001
            return []

    def repondre_avis(self, review_id, texte_reponse):
        try:
            url = "%s/reviews/%s/reply" % (self._location_path(), review_id)
            r = requests.put(
                url,
                headers=self.headers,
                json={"comment": texte_reponse},
                timeout=15,
            )
            return {"success": r.status_code == 200, "response": r.json()}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def get_location_info(self):
        try:
            r = requests.get(
                self._location_path(), headers=self.headers, timeout=15
            )
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
