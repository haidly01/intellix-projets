# -*- coding: utf-8 -*-
from odoo import fields, models


class AgentActionTag(models.Model):
    _name = "doorway.agent.action.tag"
    _description = "Action activable pour un agent IA"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
