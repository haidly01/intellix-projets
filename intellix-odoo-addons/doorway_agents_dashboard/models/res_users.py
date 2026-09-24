# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    doorway_calendar_visible = fields.Boolean(
        string="Calendrier partagé (équipe)",
        default=True,
        help="Si coché, les collègues peuvent afficher votre calendrier "
        "dans la vue Participants pour voir vos disponibilités.",
    )
    doorway_is_ai_agent_user = fields.Boolean(
        string="Compte calendrier agent IA",
        default=False,
        help="Compte technique lié à un agent IA (pas de connexion).",
    )
    doorway_agent_profile_id = fields.Many2one(
        "doorway.agent.profile",
        string="Profil agent IA",
        ondelete="set null",
    )

    @api.model
    def doorway_sync_calendar_filters(self):
        """Ajoute les filtres Participants pour voir les calendriers de l'équipe."""
        Users = self.sudo()
        visible = Users.search(
            [
                ("share", "=", False),
                ("active", "=", True),
                ("doorway_calendar_visible", "=", True),
            ]
        )
        if len(visible) < 2:
            return
        Filters = self.env["calendar.filters"].sudo()
        for user in visible:
            for colleague in visible:
                if colleague.partner_id == user.partner_id:
                    continue
                existing = Filters.search(
                    [
                        ("user_id", "=", user.id),
                        ("partner_id", "=", colleague.partner_id.id),
                    ],
                    limit=1,
                )
                if not existing:
                    Filters.create(
                        {
                            "user_id": user.id,
                            "partner_id": colleague.partner_id.id,
                            "partner_checked": True,
                            "active": True,
                        }
                    )

    def _doorway_ensure_public_calendar(self):
        for user in self:
            if user.calendar_default_privacy != "public":
                user.sudo().write({"calendar_default_privacy": "public"})
