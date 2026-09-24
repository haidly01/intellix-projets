# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPropertyEvenement(models.Model):
    _inherit = "coins.property"

    property_type = fields.Selection(
        selection_add=[("event_venue", "Événements / rooftop")],
        ondelete={"event_venue": "set default"},
    )
