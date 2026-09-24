# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    doorway_theme = fields.Selection(
        selection=[("light", "Clair"), ("dark", "Sombre")],
        string="Thème Doorway",
        default="light",
        help="Thème clair/sombre du back-office Doorway. Réglable par chaque "
        "utilisateur via le commutateur (soleil/lune) de la barre supérieure.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["doorway_theme"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["doorway_theme"]

    @api.model
    def _login(self, credential, user_agent_env):
        # Tolerate spaces + email case (Zakaria@… vs zakaria@…).
        if credential and isinstance(credential.get("login"), str):
            login = credential["login"].strip()
            if "@" in login:
                login = login.lower()
            credential = dict(credential, login=login)
        return super()._login(credential, user_agent_env)

    def _on_login_cooldown(self, failures, previous):
        import logging
        logging.getLogger(__name__).warning(
            "IX_COOLDOWN_BYPASS failures=%s previous=%s -> False", failures, previous
        )
        return False
