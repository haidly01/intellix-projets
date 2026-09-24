# -*- coding: utf-8 -*-
import functools
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    doorway_mailbox_id = fields.Many2one(
        "doorway.crm.mailbox",
        string="Boîte Doorway",
        ondelete="cascade",
        index=True,
    )

    def _fetch_mail_doorway(self, batch_limit=50):
        """Route les e-mails IMAP vers la boîte existante (thread_id)."""
        from odoo.addons.mail.models.fetchmail import MAIL_SERVER_DOMAIN

        result_exception = None
        servers = self.with_context(fetchmail_cron_running=True)
        total_remaining = len(servers)
        self.env["ir.cron"]._commit_progress(remaining=total_remaining)

        for server in servers:
            total_remaining -= 1
            if not server.try_lock_for_update(allow_referencing=True).filtered_domain(
                MAIL_SERVER_DOMAIN
            ):
                continue
            server_type_and_name = server.server_type, server.name
            count = 0
            server_connection = None
            message_cr = None
            try:
                server_connection = server._connect__()
                message_cr = self.env.registry.cursor()
                MailThread = (
                    server.env["mail.thread"]
                    .with_env(self.env(cr=message_cr))
                    .with_context(default_fetchmail_server_id=server.id)
                )
                thread_process_message = functools.partial(
                    MailThread.message_process,
                    model=server.object_id.model,
                    save_original=server.original,
                    strip_attachments=not server.attach,
                    thread_id=server.doorway_mailbox_id.id,
                )
                unread_message_count = server_connection.check_unread_messages()
                total_remaining += unread_message_count
                for message_num, message in server_connection.retrieve_unread_messages():
                    count += 1
                    total_remaining -= 1
                    try:
                        thread_process_message(message=message)
                        remaining_time = MailThread.env["ir.cron"]._commit_progress(1)
                    except Exception:  # noqa: BLE001
                        MailThread.env.cr.rollback()
                        _logger.info(
                            "Échec traitement mail %s server %s.",
                            *server_type_and_name,
                            exc_info=True,
                        )
                        remaining_time = MailThread.env["ir.cron"]._commit_progress(1)
                    server_connection.handled_message(message_num)
                    if count >= batch_limit or not remaining_time:
                        break
                server.error_date = False
                server.error_message = False
            except Exception as exc:  # noqa: BLE001
                result_exception = exc
                _logger.info(
                    "Échec fetchmail %s server %s.",
                    *server_type_and_name,
                    exc_info=True,
                )
            finally:
                if message_cr:
                    message_cr.commit()
                    message_cr.close()
                if server_connection:
                    try:
                        server_connection.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
            server.write({"date": fields.Datetime.now()})
            self.env["ir.cron"]._commit_progress(remaining=total_remaining)
        return result_exception

    def _fetch_mail(self, batch_limit=50):
        doorway_servers = self.filtered("doorway_mailbox_id")
        other_servers = self - doorway_servers
        result_exception = None
        if doorway_servers:
            result_exception = doorway_servers._fetch_mail_doorway(batch_limit=batch_limit)
        if other_servers:
            ex = super(FetchmailServer, other_servers)._fetch_mail(batch_limit=batch_limit)
            if ex is not None:
                result_exception = ex
        return result_exception
