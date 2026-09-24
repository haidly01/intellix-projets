# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayBulkSelectWizard(models.TransientModel):
    _name = "doorway.bulk.select.wizard"
    _description = "Sélection leads pour messagerie"

    pipeline_id = fields.Many2one("crm.team", string="Pipeline")
    stage_ids = fields.Many2many(
        "crm.stage",
        "doorway_bulk_wizard_stage_rel",
        "wizard_id",
        "stage_id",
        string="Étapes",
    )
    tag_ids = fields.Many2many(
        "crm.tag",
        "doorway_bulk_wizard_tag_rel",
        "wizard_id",
        "tag_id",
        string="Tags",
    )
    lead_ids = fields.Many2many(
        "crm.lead",
        "doorway_bulk_wizard_lead_rel",
        "wizard_id",
        "lead_id",
        string="Leads trouvés",
    )

    def action_rechercher(self):
        self.ensure_one()
        domain = []
        if self.pipeline_id:
            domain.append(("team_id", "=", self.pipeline_id.id))
        if self.stage_ids:
            domain.append(("stage_id", "in", self.stage_ids.ids))
        if self.tag_ids:
            domain.append(("tag_ids", "in", self.tag_ids.ids))
        leads = self.env["crm.lead"].search(domain, limit=5000)
        self.lead_ids = [(6, 0, leads.ids)]
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.bulk.select.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_ouvrir_compose(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.compose.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_source_destinataires": "leads",
                "default_lead_ids": [(6, 0, self.lead_ids.ids)],
            },
        }
