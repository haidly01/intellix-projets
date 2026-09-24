# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsQuebecPartenariatService(models.Model):
    _name = "coins.quebec.partenariat.service"
    _description = "Service & prix (fiche commerçant CQ)"
    _inherit = ["coins.quebec.cad.mixin"]
    _order = "sequence, id"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Service", required=True)
    price = fields.Monetary(string="Prix", currency_field="currency_id")
    unit = fields.Char(string="Unité")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self._cq_cad().id,
    )


class CoinsQuebecPartenariatForfait(models.Model):
    _name = "coins.quebec.partenariat.forfait"
    _description = "Forfait commerçant (fiche CQ)"
    _inherit = ["coins.quebec.cad.mixin"]
    _order = "sequence, id"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Forfait", required=True)
    price = fields.Monetary(string="Prix", currency_field="currency_id")
    unit = fields.Char(string="Détail")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self._cq_cad().id,
    )


class CoinsQuebecPartenariatPhoto(models.Model):
    _name = "coins.quebec.partenariat.photo"
    _description = "Photo fiche commerçant CQ"
    _order = "sequence, id"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    image = fields.Image(string="Photo", required=True)
    caption = fields.Char(string="Légende")
