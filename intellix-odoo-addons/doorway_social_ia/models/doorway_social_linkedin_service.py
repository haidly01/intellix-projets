# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class DoorwaySocialLinkedinService(models.AbstractModel):
    _name = "doorway.social.linkedin.service"
    _description = "Synchronisation LinkedIn (commentaires posts)"

    def sync_comments(self):
        stats = {"comments": 0, "errors": []}
        profiles = self.env["doorway.social.linkedin.profile"].search(
            [("active", "=", True)]
        )
        for profile in profiles:
            try:
                stats["comments"] += self._sync_profile_comments(profile)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("LinkedIn sync %s: %s", profile.name, exc)
                stats["errors"].append("%s: %s" % (profile.name, exc))
        return stats

    def _sync_profile_comments(self, profile):
        svc = profile._linkedin_service()
        if not svc:
            return 0
        posts = svc.lister_posts_recents(limit=10)
        count = 0
        for post in posts:
            post_urn = post.get("id") or post.get("urn") or ""
            if not post_urn:
                continue
            for comment in svc.lister_commentaires(post_urn):
                if self._upsert_comment(profile, post, comment):
                    count += 1
        return count

    def _upsert_comment(self, profile, post, comment):
        ext_id = comment.get("id") or comment.get("urn") or ""
        if not ext_id:
            return False
        author = (
            (comment.get("actor") or {}).get("name")
            or (comment.get("created", {}) or {}).get("actor", {}).get("name")
            or _("Utilisateur LinkedIn")
        )
        text = (
            comment.get("message", {}).get("text")
            or comment.get("text")
            or ""
        )
        if not text:
            return False

        Inbox = self.env["doorway.social.inbox"].sudo()
        domain = [
            ("inbox_source", "=", "linkedin"),
            ("account_id", "=", profile.account_id.id),
            ("external_id", "=", ext_id),
        ]
        conv = Inbox.search(domain, limit=1)
        preview = text[:500]
        now = fields.Datetime.now()
        post_preview = (post.get("text") or post.get("commentary") or "")[:120]

        if conv:
            return False

        conv = Inbox.create(
            {
                "name": "LinkedIn — %s" % author,
                "inbox_source": "linkedin",
                "external_id": ext_id,
                "external_name": author,
                "account_id": profile.account_id.id,
                "state": "open",
                "unread_count": 1,
                "last_message": preview,
                "last_message_date": now,
            }
        )
        self.env["doorway.social.message"].sudo().create(
            {
                "conversation_id": conv.id,
                "direction": "inbound",
                "content": preview,
                "external_msg_id": ext_id,
            }
        )
        self.env["doorway.social.comment"].sudo().create(
            {
                "conversation_id": conv.id,
                "author_name": author,
                "content": text,
                "platform": "linkedin",
                "external_comment_id": ext_id,
                "post_preview": post_preview,
                "post_url": post.get("permalink") or "",
            }
        )
        return True

    def publish_post(self, profile, text, image_url=None):
        svc = profile._linkedin_service()
        if not svc:
            return False
        if profile.profile_type == "personal":
            return svc.publier_post_personnel(text, image_url=image_url)
        return svc.publier_post_entreprise(text, image_url=image_url)
