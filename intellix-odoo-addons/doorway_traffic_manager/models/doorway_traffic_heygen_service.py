# -*- coding: utf-8 -*-
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwayTrafficHeygenService(models.AbstractModel):
    _name = "doorway.traffic.heygen.service"
    _description = "Service HeyGen — vidéos créatifs Traffic Manager"

    def generate_creative_video(self, creative):
        creative.ensure_one()
        if creative.format not in ("video", "reel", "story"):
            raise UserError(
                _("La génération HeyGen est réservée aux formats vidéo, reel ou story.")
            )
        foundation = creative.campaign_id.foundation_id
        script = (
            creative.video_script
            or creative.body
            or creative.headline
            or foundation.main_value_prop
            or ""
        )
        if not script.strip():
            raise UserError(_("Renseignez le script vidéo ou le corps du message."))

        creative.write({"video_script": script, "media_status": "video_pending"})

        HeyGen = self.env["doorway.social.heygen.service"]
        pipeline = foundation.pipeline_id
        avatar = getattr(pipeline, "heygen_avatar_id", "") or ""
        voice = getattr(pipeline, "heygen_voice_id", "") or ""

        class _HeygenPayload:
            id = creative.id
            video_script = script
            hook = creative.headline or ""
            post_format = creative.format or "video"

            def _get_avatar_id(self):
                return avatar

            def _get_voice_id(self):
                return voice

        post_like = _HeygenPayload()

        result = HeyGen.generate_video(post_like)
        video_id = result.get("video_id")
        if not video_id:
            self.env["doorway.traffic.media.service"].ensure_creative_preview(creative)
            creative.campaign_id.message_post(
                body=_(
                    "HeyGen non configuré — aperçu vidéo placeholder généré. "
                    "Configurez doorway_social_ia.heygen_api_key pour une vraie vidéo."
                )
            )
            return {"video_id": False, "status": "placeholder"}

        creative.write({"heygen_video_id": video_id})
        self.env["doorway.traffic.heygen.job"].create({
            "creative_id": creative.id,
            "heygen_video_id": video_id,
        })
        creative.campaign_id.message_post(
            body=_("Vidéo HeyGen en cours de génération pour « %s ».")
            % (creative.headline or creative.id)
        )
        return {"video_id": video_id, "status": "pending"}

    def generate_for_wizard(self, foundation, creative_data):
        """Génération vidéo HeyGen depuis le wizard (sans enregistrement créatif)."""
        foundation.ensure_one()
        fmt = creative_data.get("format") or "video"
        if fmt not in ("video", "reel", "story"):
            raise UserError(
                _("HeyGen est réservé aux formats vidéo, reel ou story.")
            )
        script = (
            creative_data.get("video_script")
            or creative_data.get("body")
            or creative_data.get("headline")
            or foundation.main_value_prop
            or ""
        )
        if not script.strip():
            raise UserError(_("Renseignez le script ou le corps du message."))

        HeyGen = self.env["doorway.social.heygen.service"]
        pipeline = foundation.pipeline_id
        avatar = getattr(pipeline, "heygen_avatar_id", "") or ""
        voice = getattr(pipeline, "heygen_voice_id", "") or ""

        class _HeygenPayload:
            id = 0
            video_script = script
            hook = creative_data.get("headline") or ""
            post_format = fmt

            def _get_avatar_id(self):
                return avatar

            def _get_voice_id(self):
                return voice

        result = HeyGen.generate_video(_HeygenPayload())
        video_id = result.get("video_id")
        Media = self.env["doorway.traffic.media.service"]
        preview_url = Media.preview_url_for_wizard(foundation, creative_data)
        if not video_id:
            return {
                "video_id": False,
                "heygen_video_id": False,
                "video_script": script,
                "video_url": "",
                "preview_url": preview_url,
                "media_status": "video_pending",
                "status": "placeholder",
                "message": _(
                    "HeyGen non configuré — script enregistré, miniature placeholder."
                ),
            }
        return {
            "video_id": video_id,
            "heygen_video_id": video_id,
            "video_script": script,
            "video_url": "",
            "preview_url": preview_url,
            "media_status": "video_pending",
            "status": "pending",
            "message": _("Vidéo HeyGen en cours de génération."),
        }
