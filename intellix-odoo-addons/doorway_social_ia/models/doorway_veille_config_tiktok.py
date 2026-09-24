# -*- coding: utf-8 -*-
from odoo import models


class DoorwayVeilleConfigTiktok(models.Model):
    _inherit = "doorway.veille.config"

    def action_connect_tiktok_publish(self):
        """Ouvre le wizard OAuth TikTok (publication, pas la veille)."""
        self.env["doorway.social.tiktok.service"].ensure_brand_tiktok_accounts()
        return {
            "type": "ir.actions.act_window",
            "name": "Connecter un compte TikTok",
            "res_model": "doorway.social.tiktok.app.wizard",
            "view_mode": "form",
            "target": "new",
        }

    def action_open_tiktok_accounts(self):
        action = self.env.ref(
            "doorway_social_ia.action_social_accounts_tiktok", raise_if_not_found=False
        )
        if action:
            return action.read()[0]
        return {
            "type": "ir.actions.act_window",
            "name": "Comptes TikTok",
            "res_model": "doorway.social.account",
            "view_mode": "kanban,list,form",
            "domain": [("platform", "=", "tiktok")],
            "context": {"default_platform": "tiktok"},
        }
