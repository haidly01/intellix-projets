# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmTeamSocial(models.Model):
    _inherit = "crm.team"

    heygen_avatar_id = fields.Char("Avatar HeyGen (défaut marque)")
    heygen_voice_id = fields.Char("Voix HeyGen (défaut marque)")
    heygen_language = fields.Selection(
        [
            ("fr", "Français (Canada)"),
            ("fr-FR", "Français (France)"),
            ("es", "Espagnol"),
            ("en", "Anglais"),
        ],
        default="fr",
    )
    social_account_ids = fields.One2many(
        "doorway.social.account", "pipeline_id", string="Comptes sociaux"
    )
