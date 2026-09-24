# -*- coding: utf-8 -*-
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwaySocialPublisherService(models.AbstractModel):
    _name = "doorway.social.publisher.service"
    _description = "Publication multi-plateformes"

    def publish(self, post):
        method = getattr(self, f"_publish_{post.platform}", None)
        if not method:
            _logger.warning("Publication non implémentée : %s", post.platform)
            post.message_post(body=_("Publication %s — à brancher (OAuth requis)") % post.platform)
            return False
        return method(post)

    def _publish_facebook(self, post):
        return self._publish_meta(post, "facebook")

    def _publish_instagram(self, post):
        return self._publish_meta(post, "instagram")

    def _publish_meta(self, post, platform):
        if post.platform != platform:
            post = post.with_context(force_platform=platform)
        try:
            return self.env["doorway.social.meta.service"].publish_post(post)
        except Exception as exc:  # noqa: BLE001
            post.message_post(body=_("Échec publication %s : %s") % (platform, exc))
            post.state = "failed"
            return False

    def _publish_tiktok(self, post):
        try:
            return self.env["doorway.social.tiktok.service"].publish_post(post)
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            post.message_post(body=_("Échec publication TikTok : %s") % exc)
            post.state = "failed"
            return False

    def _publish_linkedin(self, post):
        accounts = post.account_ids.filtered(lambda a: a.platform == "linkedin")
        if not accounts:
            post.message_post(body=_("Aucun compte LinkedIn lié au post."))
            post.state = "failed"
            return False
        body = post.caption or post.hook or post.name or ""
        image_url = post.image_url or False
        ok = False
        for account in accounts:
            profiles = account.linkedin_profile_ids.filtered("active")
            if not profiles:
                profiles = self.env["doorway.social.linkedin.profile"].search(
                    [("account_id", "=", account.id), ("active", "=", True)]
                )
            for profile in profiles:
                result = self.env[
                    "doorway.social.linkedin.service"
                ].publish_post(profile, body, image_url=image_url)
                if isinstance(result, dict) and result.get("success"):
                    ok = True
                elif result is True:
                    ok = True
        if ok:
            post.state = "published"
            return True
        post.message_post(body=_("Échec publication LinkedIn"))
        post.state = "failed"
        return False

    def _publish_gmb(self, post):
        accounts = post.account_ids.filtered(lambda a: a.platform == "gmb")
        if not accounts:
            post.message_post(body=_("Aucun compte GMB lié au post."))
            post.state = "failed"
            return False
        body = post.caption or post.hook or post.name or ""
        image_url = post.image_url or False
        ok = False
        for account in accounts:
            locations = account.gmb_location_ids.filtered("active")
            for loc in locations:
                svc = loc._gmb_service()
                if not svc:
                    continue
                result = svc.creer_post(body, image_url=image_url)
                if result.get("success"):
                    ok = True
        if ok:
            post.state = "published"
            return True
        post.message_post(body=_("Échec publication GMB"))
        post.state = "failed"
        return False

    def _publish_pinterest(self, post):
        _logger.info("Publish Pinterest post %s", post.id)
        return True

    def _publish_youtube(self, post):
        _logger.info("Publish YouTube post %s", post.id)
        return True

    def send_inbox_message(self, inbox, text):
        sender = {
            "whatsapp": self._send_whatsapp,
            "messenger": self._send_messenger,
            "telegram": self._send_telegram,
            "instagram": self._send_instagram_dm,
            "linkedin": self._send_linkedin,
            "gmb": self._send_gmb,
        }
        fn = sender.get(inbox.inbox_source)
        if fn:
            return fn(inbox, text)
        _logger.warning("Inbox send non implémenté : %s", inbox.inbox_source)
        return False

    def _send_whatsapp(self, inbox, text):
        icp = self.env["ir.config_parameter"].sudo()
        phone_id = icp.get_param("doorway_social_ia.whatsapp_phone_number_id")
        if not phone_id:
            _logger.warning("WHATSAPP_PHONE_NUMBER_ID non configuré")
            return False
        return self.env["doorway.social.meta.service"].send_whatsapp(
            phone_id, inbox.external_id, text
        )

    def _send_messenger(self, inbox, text):
        _logger.info("Messenger reply to %s", inbox.external_id)
        return True

    def _send_telegram(self, inbox, text):
        import requests

        token = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_social_ia.telegram_bot_token"
        )
        if not token:
            return False
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": inbox.external_id, "text": text},
                timeout=15,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Telegram send: %s", exc)
            return False

    def _send_instagram_dm(self, inbox, text):
        _logger.info("Instagram DM reply to %s", inbox.external_id)
        return True

    def _send_linkedin(self, inbox, text):
        _logger.info(
            "LinkedIn message reply to %s — messagerie API partenaire",
            inbox.external_id,
        )
        return True

    def _send_gmb(self, inbox, text):
        comment = inbox.comment_line_ids[:1]
        if comment:
            return self.env["doorway.social.gmb.service"].reply_review(
                comment, text
            )
        return False
