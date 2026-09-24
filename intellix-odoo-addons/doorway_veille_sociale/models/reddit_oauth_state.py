# -*- coding: utf-8 -*-
"""Session OAuth Reddit — table partagée (tous les workers / threads)."""
from datetime import timedelta

from odoo import api, fields, models

OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes


class RedditOAuthState(models.Model):
    _name = "doorway.reddit.oauth.state"
    _description = "Session OAuth Reddit temporaire"
    _rec_name = "state"

    state = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", ondelete="set null")
    config_id = fields.Many2one("doorway.veille.config", ondelete="cascade")
    code_verifier = fields.Char()
    code_challenge = fields.Char()
    redirect_uri = fields.Char()
    client_id = fields.Char()
    client_secret = fields.Char()
    consumed = fields.Boolean(default=False, index=True)
    result = fields.Selection(
        [
            ("pending", "En cours"),
            ("ok", "OK"),
            ("error", "Erreur"),
        ],
        default="pending",
    )
    result_message = fields.Char()

    _sql_constraints = [
        (
            "state_unique",
            "unique(state)",
            "Ce jeton OAuth Reddit a déjà été enregistré.",
        ),
    ]

    def age_seconds(self):
        self.ensure_one()
        created = self.create_date or fields.Datetime.now()
        return (fields.Datetime.now() - created).total_seconds()

    def is_expired(self):
        self.ensure_one()
        return self.age_seconds() > OAUTH_STATE_TTL_SECONDS

    def lock_row(self):
        """Verrouille la ligne pour éviter un double callback concurrent."""
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM doorway_reddit_oauth_state WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        return self.exists()

    @api.model
    def cleanup_expired(self):
        """Supprime les sessions de plus de 10 minutes et l'ancien stockage ICP."""
        limit = fields.Datetime.now() - timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
        expired = self.sudo().search([("create_date", "<", limit)])
        if expired:
            expired.unlink()
        icp = self.env["ir.config_parameter"].sudo()
        leftover = icp.search([("key", "like", "doorway.veille.reddit.oauth.%")])
        if leftover:
            leftover.unlink()
        return True
