# -*- coding: utf-8 -*-
import logging
import re

from odoo import _, fields, models

_logger = logging.getLogger(__name__)

_RATING_MAP = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
}


class DoorwaySocialGmbService(models.AbstractModel):
    _name = "doorway.social.gmb.service"
    _description = "Synchronisation Google My Business (avis & messages)"

    def sync_reviews(self):
        stats = {"reviews": 0, "errors": []}
        locations = self.env["doorway.social.gmb.location"].search(
            [("active", "=", True)]
        )
        for loc in locations:
            try:
                stats["reviews"] += self._sync_location_reviews(loc)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("GMB sync %s: %s", loc.name, exc)
                stats["errors"].append("%s: %s" % (loc.name, exc))
        return stats

    def _sync_location_reviews(self, location):
        svc = location._gmb_service()
        if not svc:
            return 0
        count = 0
        Inbox = self.env["doorway.social.inbox"].sudo()
        for review in svc.lister_avis():
            review_name = review.get("name") or ""
            ext_id = review_name.split("/")[-1] if review_name else ""
            if not ext_id:
                continue
            reviewer = (review.get("reviewer") or {}).get("displayName") or _("Client")
            comment = review.get("comment") or ""
            rating = review.get("starRating") or ""
            stars = _RATING_MAP.get(rating, 0)
            preview = ("%s %s" % ("★" * stars, comment)).strip()[:500]

            domain = [
                ("inbox_source", "=", "gmb"),
                ("account_id", "=", location.account_id.id),
                ("external_id", "=", ext_id),
            ]
            conv = Inbox.search(domain, limit=1)
            now = fields.Datetime.now()
            if not conv:
                conv = Inbox.create(
                    {
                        "name": "GMB — %s" % reviewer,
                        "inbox_source": "gmb",
                        "external_id": ext_id,
                        "external_name": reviewer,
                        "account_id": location.account_id.id,
                        "state": "open",
                        "unread_count": 1,
                        "last_message": preview or _("Nouvel avis"),
                        "last_message_date": now,
                    }
                )
                self.env["doorway.social.message"].sudo().create(
                    {
                        "conversation_id": conv.id,
                        "direction": "inbound",
                        "content": preview or _("(avis sans texte)"),
                        "external_msg_id": ext_id,
                    }
                )
                self._upsert_review_comment(conv, review, preview)
                count += 1
            else:
                reply = (review.get("reviewReply") or {}).get("comment")
                if reply and not conv.comment_line_ids.filtered(
                    lambda c: c.is_replied
                ):
                    conv.comment_line_ids.write(
                        {"is_replied": True, "reply_content": reply}
                    )
                elif preview and conv.last_message != preview:
                    conv.write(
                        {
                            "last_message": preview,
                            "last_message_date": now,
                            "unread_count": conv.unread_count + 1,
                            "state": "open",
                        }
                    )
                    count += 1
        return count

    def _upsert_review_comment(self, conv, review, preview):
        Comment = self.env["doorway.social.comment"].sudo()
        ext_id = conv.external_id
        existing = Comment.search(
            [
                ("conversation_id", "=", conv.id),
                ("external_comment_id", "=", ext_id),
            ],
            limit=1,
        )
        if existing:
            return existing
        reply = (review.get("reviewReply") or {}).get("comment")
        return Comment.create(
            {
                "conversation_id": conv.id,
                "author_name": conv.external_name,
                "content": preview,
                "platform": "gmb",
                "external_comment_id": ext_id,
                "is_replied": bool(reply),
                "reply_content": reply or False,
            }
        )

    def reply_review(self, comment, reply_text):
        comment.ensure_one()
        conv = comment.conversation_id
        if conv.inbox_source != "gmb":
            return False
        location = self.env["doorway.social.gmb.location"].search(
            [("account_id", "=", conv.account_id.id), ("active", "=", True)],
            limit=1,
        )
        if not location:
            return False
        svc = location._gmb_service()
        if not svc:
            return False
        review_id = comment.external_comment_id or conv.external_id
        result = svc.repondre_avis(review_id, reply_text)
        return result.get("success")
