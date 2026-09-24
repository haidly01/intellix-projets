# -*- coding: utf-8 -*-
"""Envoi email via mail.mail Odoo (SMTP Brevo / serveur configuré)."""
import logging

from odoo import fields

_logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, env):
        self.env = env

    def send_email(self, to_email, subject, body_html, recipient_name=""):
        if not to_email:
            return {"success": False, "error": "Email vide"}
        try:
            mail = self.env["mail.mail"].sudo().create(
                {
                    "subject": subject,
                    "body_html": body_html,
                    "email_to": to_email,
                    "email_from": self.env.company.email or self.env.user.email,
                    "auto_delete": False,
                    "state": "outgoing",
                }
            )
            mail.send()
            return {"success": True, "mail_id": str(mail.id)}
        except Exception as exc:  # noqa: BLE001
            _logger.error("Email send error: %s", exc)
            return {"success": False, "error": str(exc)}
