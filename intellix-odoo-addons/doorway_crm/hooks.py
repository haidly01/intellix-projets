# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Synchronise les activités CRM existantes vers calendar.event (install fraîche)."""
    count = env["mail.activity"]._doorway_migrate_existing_activities_to_calendar()
    _logger.info(
        "doorway_crm post_init: %s activité(s) CRM migrée(s) vers le calendrier",
        count,
    )
    _migrate_legacy_mailboxes(env)


def _migrate_legacy_mailboxes(env):
    """Convertit les anciennes configs fetchmail (crm.lead) en boîtes doorway.crm.mailbox."""
    Fetchmail = env["fetchmail.server"].sudo()
    Mailbox = env["doorway.crm.mailbox"].sudo()
    mailbox_model = env["ir.model"].search([("model", "=", "doorway.crm.mailbox")], limit=1)
    if not mailbox_model:
        return
    legacy = Fetchmail.search([
        ("doorway_mailbox_id", "=", False),
        ("user", "!=", False),
        "|",
        ("object_id.model", "=", "crm.lead"),
        ("object_id", "=", False),
    ])
    for server in legacy:
        user = env["res.users"].sudo().search([
            ("email", "=ilike", server.user),
        ], limit=1) or env["res.users"].sudo().search([
            ("login", "=ilike", server.user),
        ], limit=1)
        if not user:
            user = env["res.users"].sudo().search([
                ("login", "=", "karine@agencedoorway.com"),
            ], limit=1) or env.ref("base.user_admin")
        if Mailbox.search([("email", "=ilike", server.user)], limit=1):
            continue
        mailbox = Mailbox.create({
            "name": server.name or server.user,
            "user_id": user.id,
            "email": server.user,
            "password": server.password,
            "imap_server": server.server or "imap.hostinger.com",
            "imap_port": server.port or 993,
            "fetchmail_server_id": server.id,
            "create_crm_leads": False,
        })
        server.write({
            "object_id": mailbox_model.id,
            "doorway_mailbox_id": mailbox.id,
        })
        _logger.info("doorway_crm: boîte migrée pour %s", server.user)
