# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class DoorwaySocialInbox(models.Model):
    _name = "doorway.social.inbox"
    _description = "Conversation inbox réseaux sociaux"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_message_date desc, id desc"

    name = fields.Char(required=True)
    inbox_source = fields.Selection(
        [
            ("whatsapp", "WhatsApp"),
            ("messenger", "Messenger"),
            ("telegram", "Telegram"),
            ("instagram", "Instagram DM"),
            ("linkedin", "LinkedIn"),
            ("gmb", "Google My Business"),
        ],
        required=True,
    )
    external_id = fields.Char(index=True)
    external_name = fields.Char()
    external_phone = fields.Char()
    contact_avatar_url = fields.Char("Avatar URL")
    crm_lead_id = fields.Many2one("crm.lead", string="Opportunité liée")
    ai_auto_reply = fields.Boolean("Réponse auto IA", default=False)
    last_message = fields.Char("Dernier message", readonly=True)
    last_message_date = fields.Datetime(readonly=True)
    account_id = fields.Many2one("doorway.social.account", string="Compte source")

    state = fields.Selection(
        [
            ("open", "Ouvert"),
            ("read", "Lu"),
            ("replied", "Répondu"),
            ("archived", "Archivé"),
        ],
        default="open",
    )
    unread_count = fields.Integer("Messages non lus", default=0)
    has_unread_comments = fields.Boolean(
        "Commentaires non répondus",
        compute="_compute_has_unread_comments",
        store=True,
    )
    message_line_ids = fields.One2many(
        "doorway.social.message",
        "conversation_id",
        string="Messages",
    )
    comment_line_ids = fields.One2many(
        "doorway.social.comment",
        "conversation_id",
        string="Commentaires",
    )

    _unique_conv = models.Constraint(
        "UNIQUE(inbox_source, account_id, external_id)",
        "Une seule conversation par contact et par compte.",
    )

    @api.depends("comment_line_ids.is_replied")
    def _compute_has_unread_comments(self):
        for rec in self:
            rec.has_unread_comments = any(
                not c.is_replied for c in rec.comment_line_ids
            )

    def _refresh_comment_flags(self):
        self._compute_has_unread_comments()

    @staticmethod
    def _initials(name):
        if not name:
            return "?"
        parts = [p[0] for p in name.split() if p]
        return "".join(parts)[:2].upper() or "?"

    def _serialize_conv(self):
        self.ensure_one()
        return {
            "id": self.id,
            "platform": self.inbox_source,
            "contact_name": self.external_name or self.name,
            "contact_phone": self.external_phone or "",
            "contact_avatar_url": self.contact_avatar_url or "",
            "social_account_id": self.account_id.id if self.account_id else False,
            "social_account_name": self.account_id.name if self.account_id else "",
            "last_message": self.last_message or "",
            "last_message_date": fields.Datetime.to_string(self.last_message_date)
            if self.last_message_date
            else "",
            "unread_count": self.unread_count,
            "state": self.state,
            "has_unread_comments": self.has_unread_comments,
            "crm_lead_id": self.crm_lead_id.id if self.crm_lead_id else False,
            "initials": self._initials(self.external_name or self.name),
        }

    @api.model
    def _domain_from_filters(self, filters):
        filters = filters or {}
        domain = [("account_id.active", "=", True)]
        platform = filters.get("platform")
        if platform and platform != "all":
            domain.append(("inbox_source", "=", platform))
        account = filters.get("account")
        if account and account != "all":
            domain.append(("account_id", "=", int(account)))
        status = filters.get("status")
        if status == "unread":
            domain.append(("unread_count", ">", 0))
        elif status == "unreplied":
            domain.append(("state", "=", "open"))
        elif status == "comments":
            domain.append(("has_unread_comments", "=", True))
        query = (filters.get("search") or "").strip()
        if query:
            domain += [
                "|",
                ("external_name", "ilike", query),
                ("last_message", "ilike", query),
            ]
        return domain

    @api.model
    def get_inbox_list(self, filters=None):
        domain = self._domain_from_filters(filters)
        convs = self.search(domain, limit=50, order="last_message_date desc, id desc")
        return [c._serialize_conv() for c in convs]

    @api.model
    def get_inbox_accounts(self):
        accounts = self.env["doorway.social.account"].search(
            [
                ("active", "=", True),
                ("connection_state", "=", "connected"),
                (
                    "platform",
                    "in",
                    [
                        "whatsapp",
                        "messenger",
                        "telegram",
                        "instagram",
                        "facebook",
                        "linkedin",
                        "gmb",
                    ],
                ),
            ],
            order="name",
        )
        return [
            {"id": a.id, "name": a.name, "platform": a.platform} for a in accounts
        ]

    @api.model
    def action_sync_from_meta(self):
        """Synchronise toutes les plateformes (Meta, LinkedIn, GMB)."""
        return self.action_sync_all_social()

    @api.model
    def action_sync_all_social(self):
        """Synchronise Meta + LinkedIn + Google My Business."""
        stats = {"messages": 0, "comments": 0, "reviews": 0, "errors": []}
        meta = self.env["doorway.social.meta.service"].sync_meta_inbox()
        stats["messages"] += meta.get("messages", 0)
        stats["comments"] += meta.get("comments", 0)
        stats["errors"].extend(meta.get("errors") or [])

        li = self.env["doorway.social.linkedin.service"].sync_comments()
        stats["comments"] += li.get("comments", 0)
        stats["errors"].extend(li.get("errors") or [])

        gmb = self.env["doorway.social.gmb.service"].sync_reviews()
        stats["reviews"] += gmb.get("reviews", 0)
        stats["errors"].extend(gmb.get("errors") or [])
        return stats

    @api.model
    def get_inbox_thread(self, conversation_id):
        conv = self.browse(int(conversation_id))
        if not conv.exists():
            return {}
        conv.action_mark_read()
        messages = [
            {
                "id": m.id,
                "direction": m.direction,
                "content": m.content,
                "media_url": m.media_url or "",
                "media_type": m.media_type or False,
                "create_date": fields.Datetime.to_string(m.create_date),
                "author_id": m.author_id.id if m.author_id else False,
            }
            for m in conv.message_line_ids
        ]
        comments = [
            {
                "id": c.id,
                "author_name": c.author_name or "",
                "content": c.content,
                "is_replied": c.is_replied,
                "reply_content": c.reply_content or "",
                "post_preview": c.post_preview or "",
                "create_date": fields.Datetime.to_string(c.create_date),
            }
            for c in conv.comment_line_ids
        ]
        return {
            "conversation": conv._serialize_conv(),
            "messages": messages,
            "comments": comments,
        }

    @api.model
    def post_incoming(self, source, from_id, from_name, text, media_url=None, phone=None):
        """Rétrocompatibilité webhooks existants."""
        return self._handle_inbound(
            platform=source,
            external_id=from_id,
            content=text or "",
            contact_name=from_name,
            contact_phone=phone,
            media_url=media_url,
        )

    @api.model
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
        account = self.env["doorway.social.account"].browse()
        if account_id:
            account = self.env["doorway.social.account"].browse(int(account_id))
        elif account_phone:
            account = self.env["doorway.social.account"].sudo().search(
                [
                    ("platform", "=", platform),
                    ("external_account_id", "=", str(account_phone)),
                    ("connection_state", "=", "connected"),
                ],
                limit=1,
            )
        domain = [
            ("inbox_source", "=", platform),
            ("external_id", "=", str(external_id)),
        ]
        if account:
            domain.append(("account_id", "=", account.id))
        channel = self.search(domain, limit=1)

        preview = (content or "")[:500]
        now = fields.Datetime.now()
        if not channel:
            channel = self.create(
                {
                    "name": f"{platform.title()} — {contact_name or external_id}",
                    "inbox_source": platform,
                    "external_id": str(external_id),
                    "external_name": contact_name,
                    "external_phone": contact_phone,
                    "account_id": account.id if account else False,
                    "state": "open",
                    "unread_count": 1,
                    "last_message": preview,
                    "last_message_date": now,
                }
            )
        else:
            vals = {
                "unread_count": channel.unread_count + 1,
                "last_message": preview or channel.last_message,
                "last_message_date": now,
            }
            if contact_name:
                vals["external_name"] = contact_name
            if channel.state in ("read", "replied"):
                vals["state"] = "open"
            channel.write(vals)

        self.env["doorway.social.message"].create(
            {
                "conversation_id": channel.id,
                "direction": "inbound",
                "content": content or _("(média)"),
                "media_url": media_url,
                "external_msg_id": external_msg_id,
            }
        )

        body = content or ""
        if media_url:
            body += f'\n<a href="{media_url}">Média</a>'
        if body:
            channel.message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

        if not channel.crm_lead_id:
            channel._maybe_create_lead()

        if channel.ai_auto_reply and content:
            reply = channel._claude_auto_reply(content)
            if reply:
                channel.action_send_message(reply)

        return channel

    def action_mark_read(self):
        for rec in self:
            rec.write({"state": "read", "unread_count": 0})
            rec.message_line_ids.filtered(
                lambda m: m.direction == "inbound" and not m.is_read
            ).write({"is_read": True})
        return True

    def action_send_message(self, text):
        self.ensure_one()
        text = (text or "").strip()
        if not text:
            return False
        self.env["doorway.social.publisher.service"].send_inbox_message(self, text)
        self.env["doorway.social.message"].create(
            {
                "conversation_id": self.id,
                "direction": "outbound",
                "content": text,
                "author_id": self.env.uid,
                "is_read": True,
            }
        )
        self.write(
            {
                "state": "replied",
                "last_message": text[:500],
                "last_message_date": fields.Datetime.now(),
            }
        )
        self.message_post(
            body=text,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            author_id=self.env.user.partner_id.id,
        )
        return True

    def action_ai_reply_suggestion(self):
        self.ensure_one()
        return (
            self.env["doorway.social.claude.service"].suggest_inbox_reply(self) or ""
        )

    def action_create_lead(self):
        self.ensure_one()
        if self.crm_lead_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "crm.lead",
                "res_id": self.crm_lead_id.id,
                "view_mode": "form",
            }
        team = self.env["crm.team"].search([], limit=1)
        lead = self.env["crm.lead"].create(
            {
                "name": f"{self.inbox_source.title()} — {self.external_name or self.name}",
                "contact_name": self.external_name,
                "mobile": self.external_phone,
                "phone": self.external_phone,
                "description": self.last_message,
                "type": "lead",
                "team_id": team.id if team else False,
            }
        )
        self.crm_lead_id = lead.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": lead.id,
            "view_mode": "form",
        }

    def _maybe_create_lead(self):
        self.ensure_one()
        if self.crm_lead_id:
            return
        team = self.env["crm.team"].search([], limit=1)
        lead = self.env["crm.lead"].create(
            {
                "name": self.external_name or self.name,
                "type": "lead",
                "team_id": team.id if team else False,
                "phone": self.external_phone,
                "description": _("Lead créé depuis %s") % self.inbox_source,
            }
        )
        self.crm_lead_id = lead.id

    def _claude_auto_reply(self, text):
        self.ensure_one()
        return self.env["doorway.social.claude.service"].auto_reply(self, text)
