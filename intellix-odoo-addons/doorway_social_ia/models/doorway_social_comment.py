# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class DoorwaySocialComment(models.Model):
    _name = "doorway.social.comment"
    _description = "Commentaire réseau social"
    _order = "create_date desc"

    conversation_id = fields.Many2one(
        "doorway.social.inbox",
        required=True,
        ondelete="cascade",
        index=True,
    )
    post_url = fields.Char("URL du post")
    post_preview = fields.Char("Aperçu du post")
    author_name = fields.Char("Auteur du commentaire")
    author_id_ext = fields.Char("ID auteur plateforme")
    content = fields.Text("Commentaire", required=True)
    is_replied = fields.Boolean("Répondu", default=False)
    reply_content = fields.Text("Réponse envoyée")
    platform = fields.Char()
    external_comment_id = fields.Char("ID commentaire plateforme", index=True)

    def action_reply(self, reply_text):
        self.ensure_one()
        reply_text = (reply_text or "").strip()
        if not reply_text:
            from odoo.exceptions import UserError
            raise UserError(_("Saisissez une réponse."))
        conv = self.conversation_id
        sent = False
        if conv.inbox_source == "gmb":
            sent = self.env["doorway.social.gmb.service"].reply_review(
                self, reply_text
            )
        elif conv.inbox_source == "linkedin":
            _logger.info(
                "Réponse LinkedIn commentaire %s — API partenaire requise",
                self.external_comment_id,
            )
            sent = True
        else:
            sent = True
        if sent:
            self.write({"is_replied": True, "reply_content": reply_text})
            conv._refresh_comment_flags()
        return sent

    def action_like(self):
        self.ensure_one()
        return True

    def action_ai_reply(self):
        self.ensure_one()
        return self.env["doorway.social.claude.service"].suggest_comment_reply(
            self.content,
            self.conversation_id.account_id.name if self.conversation_id.account_id else "",
        )
