# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsQuebecPrestataireTag(models.Model):
    _name = "coins.quebec.prestataire.tag"
    _description = "Tag prestataire (Coins Québec)"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer()


class CoinsQuebecPrestataire(models.Model):
    _name = "coins.quebec.prestataire"
    _description = "Prestataire CRM (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one("res.partner")
    category = fields.Selection(
        [
            ("photo", "Photo / vidéo"),
            ("traiteur", "Traiteur"),
            ("fleuriste", "Fleuriste"),
            ("dj", "DJ / animation"),
            ("other", "Autre"),
        ],
        default="other",
    )
    phone = fields.Char()
    email = fields.Char()
    city = fields.Char()
    tag_ids = fields.Many2many("coins.quebec.prestataire.tag", string="Tags")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    tarif = fields.Monetary(currency_field="currency_id")
    notes = fields.Text()
