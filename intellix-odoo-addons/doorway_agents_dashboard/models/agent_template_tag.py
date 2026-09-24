# -*- coding: utf-8 -*-
from odoo import fields, models


class AgentTemplateTag(models.Model):
    _name = "doorway.agent.template.tag"
    _description = "Tag de template agent IA"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
