# -*- coding: utf-8 -*-
from odoo import models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _doorway_public_url(self):
        """URL publiquement atteignable d'un média (pour preview + Instagram).

        Instagram exige une `image_url` / `video_url` accessible par les
        serveurs Meta. On génère un access_token et on construit une URL
        /web/content signée, valable tant que le serveur Odoo est exposé.
        """
        self.ensure_one()
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        token = self.sudo().access_token
        if not token:
            token = self.sudo().generate_access_token()[0]
        return "%s/web/content/%s?access_token=%s&download=true" % (
            base_url,
            self.id,
            token,
        )
