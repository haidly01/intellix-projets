# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySocialConnectWizard(models.TransientModel):
    _name = "doorway.social.connect.wizard"
    _description = "Importer comptes Meta depuis Veille"

    pipeline_id = fields.Many2one("crm.team", string="Marque / Pipeline")

    def action_import_meta_from_veille(self):
        accounts = self.env["doorway.social.meta.service"].sync_all_meta_pages()
        if self.pipeline_id and accounts:
            accounts.filtered(lambda a: not a.pipeline_id).write(
                {"pipeline_id": self.pipeline_id.id}
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Comptes connectés",
            "res_model": "doorway.social.account",
            "view_mode": "kanban,list,form",
            "domain": [("platform", "in", ["facebook", "instagram"])],
        }
