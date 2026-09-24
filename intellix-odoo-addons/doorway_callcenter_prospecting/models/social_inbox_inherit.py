# -*- coding: utf-8 -*-
from odoo import models


class DoorwaySocialInboxCallcenter(models.Model):
    _inherit = "doorway.social.inbox"

    def _handle_inbound(
        self,
        platform,
        external_id,
        content="",
        contact_name=None,
        contact_phone=None,
        account_phone=None,
        account_id=None,
        media_url=None,
        external_msg_id=None,
    ):
        thread = super()._handle_inbound(
            platform,
            external_id,
            content=content,
            contact_name=contact_name,
            contact_phone=contact_phone,
            account_phone=account_phone,
            account_id=account_id,
            media_url=media_url,
            external_msg_id=external_msg_id,
        )
        if platform == "whatsapp" and content:
            phone = contact_phone or external_id
            self.env["doorway.callcenter.prospect"].sudo().process_incoming_reply(
                phone,
                content,
                profile_name=contact_name,
            )
        return thread
