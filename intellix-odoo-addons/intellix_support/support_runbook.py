# -*- coding: utf-8 -*-
from odoo import fields, models


class IntellixSupportRunbook(models.Model):
    _name = "intellix.support.runbook"
    _description = "Runbook correctif support"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one("intellix.support.category")
    description = fields.Html()
    active = fields.Boolean(default=True)
    requires_approval = fields.Boolean(
        string="Approbation requise",
        default=True,
    )
    phase = fields.Selection(
        [
            ("mvp", "MVP — lecture seule"),
            ("ready", "Prêt à exécuter"),
            ("planned", "Planifié"),
        ],
        default="planned",
    )

    @api.model
    def _init_runbook_phases(self):
        """Phase A — active le runbook pilote access_denied."""
        runbook = self.env.ref(
            "intellix_support.runbook_access_denied", raise_if_not_found=False
        )
        if runbook and runbook.phase != "ready":
            runbook.sudo().write({"phase": "ready", "requires_approval": True})
