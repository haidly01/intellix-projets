# -*- coding: utf-8 -*-
import email
import imaplib
import logging
import re
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

_IMAP_FOLDERS = {
    "inbox": ("INBOX",),
    "sent": ("Sent", "INBOX.Sent", "Sent Items", "INBOX.Sent Items"),
    "junk": ("Junk", "INBOX.Junk", "Spam", "INBOX.Spam"),
    "trash": ("Trash", "INBOX.Trash", "Deleted Items", "INBOX.Trash"),
}

_logger = logging.getLogger(__name__)


class DoorwayCrmMailbox(models.Model):
    _name = "doorway.crm.mailbox"
    _description = "Boîte mail CRM"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "is_default desc, email"

    name = fields.Char(string="Libellé", required=True)
    user_id = fields.Many2one(
        "res.users",
        string="Propriétaire",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    shared_user_ids = fields.Many2many(
        "res.users",
        "doorway_crm_mailbox_shared_user_rel",
        "mailbox_id",
        "user_id",
        string="Accès partagé",
        help="Utilisateurs autorisés à lire et envoyer depuis cette boîte.",
    )
    email = fields.Char(string="Adresse e-mail", required=True, index=True)
    password = fields.Char(string="Mot de passe")
    imap_server = fields.Char(default="imap.hostinger.com", required=True)
    imap_port = fields.Integer(default=993, required=True)
    smtp_server = fields.Char(default="smtp.hostinger.com", required=True)
    smtp_port = fields.Integer(default=465, required=True)
    smtp_encryption = fields.Selection(
        [("ssl", "SSL/TLS"), ("starttls", "STARTTLS"), ("none", "Aucun")],
        default="ssl",
        required=True,
    )
    is_default = fields.Boolean(string="Boîte par défaut (envoi)", default=False)
    active = fields.Boolean(default=True)
    create_crm_leads = fields.Boolean(
        string="Créer des pistes CRM (nouveaux expéditeurs)",
        default=False,
        help="Si coché, les e-mails de nouveaux contacts créent une piste CRM. "
        "Les expéditeurs déjà connus sont rattachés au fil existant sans erreur.",
    )
    fetchmail_server_id = fields.Many2one("fetchmail.server", ondelete="set null", copy=False)
    mail_server_id = fields.Many2one("ir.mail_server", ondelete="set null", copy=False)
    message_count = fields.Integer(compute="_compute_message_count")

    _sql_constraints = [
        (
            "doorway_mailbox_email_user_uniq",
            "unique(user_id, email)",
            "Cette adresse est déjà configurée pour votre compte.",
        ),
    ]

    @api.depends("message_ids")
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_mail_servers()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"email", "password", "imap_server", "imap_port", "smtp_server", "smtp_port",
            "smtp_encryption", "active", "create_crm_leads"} & set(vals.keys()):
            self._sync_mail_servers()
        if vals.get("is_default"):
            others = self.search([
                ("user_id", "in", self.mapped("user_id").ids),
                ("id", "not in", self.ids),
                ("is_default", "=", True),
            ])
            others.write({"is_default": False})
        return res

    def _crm_lead_model(self):
        return self.env["ir.model"].sudo().search([("model", "=", "crm.lead")], limit=1)

    def _mailbox_model(self):
        return self.env["ir.model"].sudo().search([("model", "=", "doorway.crm.mailbox")], limit=1)

    def _sync_mail_servers(self):
        mailbox_model = self._mailbox_model()
        if not mailbox_model:
            return

        for mailbox in self:
            if not mailbox.email or "@" not in mailbox.email:
                continue
            try:
                with self.env.cr.savepoint():
                    self._sync_mail_server_single(mailbox, mailbox_model)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Sync serveurs mail échouée pour %s: %s",
                    mailbox.email,
                    exc,
                    exc_info=True,
                )

    def _sync_mail_server_single(self, mailbox, mailbox_model):
        Fetchmail = self.env["fetchmail.server"].sudo()
        MailServer = self.env["ir.mail_server"].sudo()
        name = _("Boîte %s") % mailbox.email
        incoming_vals = {
            "name": name,
            "server_type": "imap",
            "server": mailbox.imap_server,
            "port": mailbox.imap_port,
            "is_ssl": True,
            "user": mailbox.email,
            "password": mailbox.password,
            "object_id": mailbox_model.id,
            "doorway_mailbox_id": mailbox.id,
            "active": mailbox.active,
        }
        incoming = mailbox.fetchmail_server_id
        if incoming:
            incoming.write(incoming_vals)
        else:
            incoming = Fetchmail.create({**incoming_vals, "state": "draft"})
            mailbox.fetchmail_server_id = incoming.id
        if mailbox.active and mailbox.password:
            try:
                incoming.button_confirm_login()
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Connexion IMAP échouée pour %s: %s", mailbox.email, exc
                )

        smtp_vals = {
            "name": name,
            "smtp_host": mailbox.smtp_server,
            "smtp_port": mailbox.smtp_port,
            "smtp_user": mailbox.email,
            "smtp_pass": mailbox.password,
            "smtp_encryption": mailbox.smtp_encryption,
            "from_filter": mailbox.email,
            "sequence": 5,
            "active": mailbox.active,
        }
        outgoing = mailbox.mail_server_id
        if outgoing:
            outgoing.write(smtp_vals)
        else:
            outgoing = MailServer.with_context(
                doorway_mailbox_sync=True,
            ).create(smtp_vals)
            mailbox.mail_server_id = outgoing.id

    def action_open_messages(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "doorway_crm_webmail_action",
            "params": {"mailbox_id": self.id},
        }

    def action_open_webmail(self):
        return {
            "type": "ir.actions.client",
            "tag": "doorway_crm_webmail_action",
        }

    def _doorway_user_can_access_mailbox(self, mailbox, user=None):
        user = user or self.env.user
        return mailbox.user_id == user or user in mailbox.shared_user_ids

    def _doorway_check_mailbox_access(self, mailbox):
        mailbox.ensure_one()
        if not self._doorway_user_can_access_mailbox(mailbox):
            raise AccessError(_("Vous n'avez pas accès à cette boîte mail."))
        return mailbox

    def _doorway_mailboxes_for_user(self, user=None):
        user = user or self.env.user
        mailboxes = self.search([
            ("active", "=", True),
            "|",
            ("user_id", "=", user.id),
            ("shared_user_ids", "in", user.id),
        ])
        owned = mailboxes.filtered(lambda mb: mb.user_id == user)
        shared = mailboxes - owned
        return owned.sorted(
            lambda mb: (not mb.is_default, mb.email or "")
        ) + shared.sorted(
            lambda mb: (not mb.is_default, mb.email or "")
        )

    @api.model
    def get_webmail_mailboxes(self):
        user = self.env.user
        mailboxes = self._doorway_mailboxes_for_user(user)
        return [{
            "id": mb.id,
            "name": mb.name,
            "email": mb.email,
            "is_default": bool(mb.is_default),
            "is_owner": mb.user_id == user,
            "message_count": mb.sudo().message_count,
        } for mb in mailboxes]

    @staticmethod
    def _doorway_extract_email(addr):
        if not addr:
            return ""
        _name, email = parseaddr(addr.strip())
        return (email or addr).strip().lower()

    @staticmethod
    def _doorway_sender_display(addr):
        if not addr:
            return _("Inconnu")
        name, email = parseaddr(addr.strip())
        return name or email or addr

    @staticmethod
    def _doorway_message_snippet(body, max_len=120):
        text = html2plaintext(body or "").strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) > max_len:
            return text[: max_len - 1] + "…"
        return text or _("(sans contenu)")

    def _doorway_message_to_dict(self, message, mailbox_email):
        email_from = message.email_from or ""
        mailbox_addr = self._doorway_extract_email(mailbox_email)
        from_addr = self._doorway_extract_email(email_from)
        direction = "outbound" if from_addr == mailbox_addr else "inbound"
        return {
            "id": message.id,
            "subject": message.subject or _("(sans objet)"),
            "email_from": email_from,
            "sender": self._doorway_sender_display(email_from),
            "date": fields.Datetime.to_string(message.date) if message.date else "",
            "snippet": self._doorway_message_snippet(message.body),
            "direction": direction,
            "attachment_count": len(message.attachment_ids),
        }

    def _imap_connect(self, mailbox):
        mailbox = mailbox.sudo()
        if not mailbox.password or not mailbox.imap_server:
            raise UserError(_("IMAP non configuré pour %s.") % mailbox.email)
        client = imaplib.IMAP4_SSL(mailbox.imap_server, mailbox.imap_port, timeout=15)
        client.login(mailbox.email, mailbox.password)
        return client

    def _imap_select_folder(self, client, folder):
        names = _IMAP_FOLDERS.get(folder) or (folder,)
        typ, folders = client.list()
        listed = []
        if typ == "OK" and folders:
            for raw in folders:
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                listed.append(line.split(' "/" ')[-1].strip().strip('"'))
        for name in names:
            if client.select(name, readonly=True)[0] == "OK":
                return name
            for listed_name in listed:
                if listed_name.lower() == name.lower() or listed_name.lower().endswith(
                    "." + name.lower()
                ):
                    if client.select(listed_name, readonly=True)[0] == "OK":
                        return listed_name
        raise UserError(_("Dossier introuvable: %s") % folder)

    @staticmethod
    def _imap_decode_header(value):
        if not value:
            return ""
        parts = []
        for chunk, charset in decode_header(value):
            if isinstance(chunk, bytes):
                parts.append(chunk.decode(charset or "utf-8", "replace"))
            else:
                parts.append(chunk)
        return "".join(parts)

    def _imap_list_messages(self, mailbox, folder, search="", limit=80, offset=0):
        client = self._imap_connect(mailbox)
        try:
            selected = self._imap_select_folder(client, folder)
            criterion = "ALL"
            if search:
                safe = search.replace('"', "").replace("\\", "")[:80]
                criterion = '(OR OR SUBJECT "%s" FROM "%s" BODY "%s")' % (safe, safe, safe)
            typ, data = client.search(None, criterion)
            if typ != "OK" or not data or not data[0]:
                return [], 0
            uids = data[0].split()
            total = len(uids)
            page = list(reversed(uids))[offset: offset + limit]
            messages = []
            for uid in page:
                typ, fetched = client.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if typ != "OK" or not fetched or not fetched[0]:
                    continue
                raw = fetched[0][1] if isinstance(fetched[0], tuple) else fetched[0]
                hdr = email.message_from_bytes(raw or b"")
                email_from = self._imap_decode_header(hdr.get("From"))
                subject = self._imap_decode_header(hdr.get("Subject")) or _("(sans objet)")
                date_raw = hdr.get("Date") or ""
                try:
                    date_val = parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    date_val = ""
                messages.append({
                    "id": "imap:%s:%s" % (selected, uid.decode() if isinstance(uid, bytes) else uid),
                    "subject": subject,
                    "email_from": email_from,
                    "sender": self._doorway_sender_display(email_from),
                    "date": date_val,
                    "snippet": "",
                    "direction": "inbound" if folder != "sent" else "outbound",
                    "attachment_count": 0,
                })
            return messages, total
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _imap_get_message(self, mailbox, message_id):
        _prefix, folder_name, uid = message_id.split(":", 2)
        client = self._imap_connect(mailbox)
        try:
            if client.select(folder_name, readonly=True)[0] != "OK":
                raise UserError(_("Message introuvable."))
            typ, fetched = client.fetch(uid.encode() if isinstance(uid, str) else uid, "(RFC822)")
            if typ != "OK" or not fetched or not fetched[0]:
                raise UserError(_("Message introuvable."))
            raw = fetched[0][1] if isinstance(fetched[0], tuple) else fetched[0]
            msg = email.message_from_bytes(raw or b"")
            email_from = self._imap_decode_header(msg.get("From"))
            subject = self._imap_decode_header(msg.get("Subject")) or _("(sans objet)")
            date_raw = msg.get("Date") or ""
            try:
                date_val = parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                date_val = ""
            html_body = ""
            text_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    decoded = payload.decode(charset, "replace")
                    if ctype == "text/html" and not html_body:
                        html_body = decoded
                    elif ctype == "text/plain" and not text_body:
                        text_body = decoded
            else:
                payload = msg.get_payload(decode=True) or b""
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, "replace")
                if msg.get_content_type() == "text/html":
                    html_body = decoded
                else:
                    text_body = decoded
            body_html = html_body or ("<pre>%s</pre>" % escape(text_body or ""))
            return {
                "id": message_id,
                "subject": subject,
                "email_from": email_from,
                "sender": self._doorway_sender_display(email_from),
                "date": date_val,
                "snippet": self._doorway_message_snippet(body_html),
                "direction": "inbound",
                "attachment_count": 0,
                "body_html": body_html,
                "reply_to": self._imap_decode_header(msg.get("Reply-To")) or email_from,
                "attachments": [],
                "mailbox_id": mailbox.id,
                "mailbox_email": mailbox.email,
            }
        finally:
            try:
                client.logout()
            except Exception:
                pass

    @api.model
    def get_webmail_messages(self, mailbox_id, folder="inbox", search="", limit=80, offset=0):
        mailbox = self.browse(mailbox_id)
        if not mailbox.exists():
            return {"messages": [], "total": 0}
        self._doorway_check_mailbox_access(mailbox)
        limit = min(int(limit or 80), 150)
        offset = max(int(offset or 0), 0)
        if folder in ("inbox", "sent", "junk", "trash"):
            try:
                messages, total = self._imap_list_messages(
                    mailbox, folder, search=search, limit=limit, offset=offset
                )
                return {"messages": messages, "total": total}
            except UserError:
                if folder in ("junk", "trash"):
                    raise
            except Exception as exc:
                _logger.warning("IMAP list %s/%s: %s", mailbox.email, folder, exc)
                if folder in ("junk", "trash"):
                    raise UserError(
                        _("Impossible de lire %s pour %s.") % (folder, mailbox.email)
                    )
        Message = self.env["mail.message"].sudo()
        domain = [
            ("model", "=", "doorway.crm.mailbox"),
            ("res_id", "=", mailbox.id),
            ("message_type", "=", "email"),
        ]
        if search:
            domain += [
                "|", "|",
                ("subject", "ilike", search),
                ("email_from", "ilike", search),
                ("body", "ilike", search),
            ]
        mailbox_addr = self._doorway_extract_email(mailbox.email)
        if folder == "inbox":
            domain += [("email_from", "not ilike", mailbox_addr)]
        elif folder == "sent":
            domain += [("email_from", "ilike", mailbox_addr)]
        total = Message.search_count(domain)
        page = Message.search(domain, order="date desc, id desc", limit=limit, offset=offset)
        return {
            "messages": [self._doorway_message_to_dict(m, mailbox.email) for m in page],
            "total": total,
        }

    @api.model
    def get_webmail_message(self, message_id, mailbox_id=None):
        if isinstance(message_id, str) and message_id.startswith("imap:"):
            mailbox = self.browse(int(mailbox_id or 0))
            if not mailbox.exists():
                raise UserError(_("Rouvrir le message depuis la liste."))
            self._doorway_check_mailbox_access(mailbox)
            return self._imap_get_message(mailbox, message_id)
        message = self.env["mail.message"].sudo().browse(int(message_id))
        if not message.exists() or message.model != "doorway.crm.mailbox":
            raise UserError(_("Message introuvable."))
        mailbox = self.browse(message.res_id)
        self._doorway_check_mailbox_access(mailbox)
        attachments = [{
            "id": att.id,
            "name": att.name,
            "mimetype": att.mimetype,
            "url": f"/web/content/{att.id}?download=true",
        } for att in message.attachment_ids]
        data = self._doorway_message_to_dict(message, mailbox.email)
        data.update({
            "body_html": message.body or "",
            "reply_to": message.reply_to or "",
            "attachments": attachments,
            "mailbox_id": mailbox.id,
            "mailbox_email": mailbox.email,
        })
        return data

    WEBMAIL_MAX_ATTACHMENTS = 10
    WEBMAIL_MAX_ATTACHMENTS_BYTES = 20 * 1024 * 1024

    def _doorway_webmail_create_attachments(self, mailbox, attachments):
        """Crée les pièces jointes envoyées par le webmail (liste de {name, mimetype, data base64})."""
        import base64
        import binascii
        import mimetypes
        if not attachments:
            return []
        if len(attachments) > self.WEBMAIL_MAX_ATTACHMENTS:
            raise UserError(_("Maximum %s pièces jointes par message.") % self.WEBMAIL_MAX_ATTACHMENTS)
        total = 0
        vals_list = []
        for att in attachments:
            name = (att.get("name") or "").replace("/", "_").replace("\\", "_").strip() or "piece-jointe"
            try:
                raw = base64.b64decode(att.get("data") or "", validate=True)
            except (binascii.Error, ValueError):
                raise UserError(_("La pièce jointe « %s » est illisible.") % name)
            if not raw:
                raise UserError(_("La pièce jointe « %s » est vide.") % name)
            total += len(raw)
            if total > self.WEBMAIL_MAX_ATTACHMENTS_BYTES:
                raise UserError(_("Les pièces jointes dépassent %s Mo au total.")
                                % (self.WEBMAIL_MAX_ATTACHMENTS_BYTES // (1024 * 1024)))
            vals_list.append({
                "name": name,
                "datas": base64.b64encode(raw),
                "mimetype": att.get("mimetype") or mimetypes.guess_type(name)[0] or "application/octet-stream",
                "res_model": "doorway.crm.mailbox",
                "res_id": mailbox.id,
            })
        return self.env["ir.attachment"].sudo().create(vals_list).ids

    @api.model
    def action_send_webmail(self, mailbox_id, to_addrs, subject, body_html,
                            cc_addrs="", bcc_addrs="", reply_message_id=None, attachments=None):
        mailbox = self.browse(mailbox_id)
        if not mailbox.exists():
            raise UserError(_("Boîte mail introuvable."))
        self._doorway_check_mailbox_access(mailbox)
        if not mailbox.mail_server_id:
            raise UserError(_("Serveur SMTP non configuré pour %s.") % mailbox.email)
        to_addrs = (to_addrs or "").strip()
        if not to_addrs:
            raise UserError(_("Indiquez au moins un destinataire."))
        if not subject:
            raise UserError(_("Indiquez un objet."))
        if not body_html or not html2plaintext(body_html).strip():
            raise UserError(_("Le message est vide."))

        mail_vals = {
            "mail_server_id": mailbox.mail_server_id.id,
            "email_from": mailbox.email,
            "email_to": to_addrs,
            "subject": subject,
            "body_html": body_html,
            "auto_delete": False,
        }
        if cc_addrs:
            mail_vals["email_cc"] = cc_addrs
        # Odoo 19 : pas de champ email_bcc sur mail.mail — Bcc via en-têtes SMTP.
        if bcc_addrs:
            mail_vals["headers"] = repr({"Bcc": bcc_addrs})
        att_ids = self._doorway_webmail_create_attachments(mailbox, attachments)
        if att_ids:
            mail_vals["attachment_ids"] = [(6, 0, att_ids)]
        mail = self.env["mail.mail"].sudo().create(mail_vals)
        mail.send()

        mailbox.message_post(
            body=body_html,
            subject=subject,
            message_type="email",
            subtype_xmlid="mail.mt_comment",
            email_from=mailbox.email,
            attachment_ids=att_ids,
        )
        return {"ok": True, "mail_id": mail.id}

    def action_fetch_now(self):
        for mailbox in self:
            self._doorway_check_mailbox_access(mailbox)
            server = mailbox.sudo().fetchmail_server_id
            if server and server.state == "done":
                server.sudo().fetch_mail()
        return True

    def _doorway_maybe_create_lead(self, msg_dict):
        """Crée ou met à jour une piste CRM sans bloquer sur e-mail déjà connu."""
        self.ensure_one()
        if not self.create_crm_leads:
            return
        email_from = (msg_dict.get("email_from") or msg_dict.get("from") or "").strip()
        if not email_from or email_from == "email not available":
            return
        Lead = self.env["crm.lead"].with_context(
            doorway_skip_email_unique_check=True,
            default_fetchmail_server_id=self.fetchmail_server_id.id,
        )
        from odoo.tools import email_normalize
        normalized = email_normalize(email_from)
        domain = [("email_from", "=ilike", email_from)]
        if normalized:
            domain = ["|", ("email_from", "=ilike", email_from), ("email_normalized", "=", normalized)]
        existing = Lead.search(domain, limit=1, order="id desc")
        if existing:
            existing.message_post(
                body=msg_dict.get("body") or _("Nouvel e-mail reçu."),
                subject=msg_dict.get("subject"),
                message_type="email",
                subtype_xmlid="mail.mt_note",
            )
            return
        Lead.create({
            "name": msg_dict.get("subject") or email_from,
            "email_from": email_from,
            "type": "lead",
            "user_id": self.user_id.id,
            "description": msg_dict.get("body"),
        })

    def message_update(self, msg_dict, update_vals=None):
        res = super().message_update(msg_dict, update_vals=update_vals)
        self._doorway_maybe_create_lead(msg_dict)
        return res
