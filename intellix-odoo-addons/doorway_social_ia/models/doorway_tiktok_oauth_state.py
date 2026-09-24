# -*- coding: utf-8 -*-
"""Session OAuth TikTok — table partagée (jamais en mémoire process)."""
from datetime import timedelta

from odoo import api, fields, models

OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes


class DoorwayTiktokOAuthState(models.Model):
    _name = "doorway.tiktok.oauth.state"
    _description = "Session OAuth TikTok temporaire"
    _rec_name = "state"

    state = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", ondelete="set null")
    account_id = fields.Many2one("doorway.social.account", ondelete="cascade")
    redirect_uri = fields.Char()
    client_key = fields.Char()
    client_secret = fields.Char()
    consumed = fields.Boolean(default=False, index=True)
    result = fields.Selection(
        [("pending", "En cours"), ("ok", "OK"), ("error", "Erreur")],
        default="pending",
    )
    result_message = fields.Char()

    _sql_constraints = [
        (
            "state_unique",
            "unique(state)",
            "Ce jeton OAuth TikTok a déjà été enregistré.",
        ),
    ]

    def is_expired(self):
        self.ensure_one()
        created = self.create_date or fields.Datetime.now()
        return (fields.Datetime.now() - created).total_seconds() > OAUTH_STATE_TTL_SECONDS

    def lock_row(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM doorway_tiktok_oauth_state WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        return self.exists()

    @api.model
    def cleanup_expired(self):
        limit = fields.Datetime.now() - timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
        expired = self.sudo().search([("create_date", "<", limit)])
        if expired:
            expired.unlink()
        return True
