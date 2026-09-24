# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEngineLegalJurisdiction(models.Model):
    _name = "pe.legal.jurisdiction"
    _description = "Juridiction droit du travail"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    country = fields.Selection(
        [("CA", "Canada"), ("FR", "France"), ("MA", "Maroc")], required=True
    )
    province_state = fields.Char(string="Province / État")
    main_law = fields.Char(string="Loi principale")
    article_ids = fields.One2many("pe.legal.article", "jurisdiction_id")
    article_count = fields.Integer(compute="_compute_article_count")

    _code_unique = models.Constraint("unique(code)", "Le code juridiction doit être unique.")

    @api.depends("article_ids")
    def _compute_article_count(self):
        for rec in self:
            rec.article_count = len(rec.article_ids)
