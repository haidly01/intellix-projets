# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    callcenter_prospect_id = fields.Many2one(
        "doorway.callcenter.prospect",
        string="Prospect call center",
        ondelete="set null",
    )
    callcenter_last_contact = fields.Datetime(string="Dernier contact campagne CC")
    callcenter_reply_intent = fields.Char(string="Intent réponse CC")
