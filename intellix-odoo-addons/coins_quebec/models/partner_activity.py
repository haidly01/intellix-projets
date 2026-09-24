# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsQuebecPartnerActivity(models.Model):
    _name = "coins.quebec.partner.activity"
    _description = "Partenaire activité (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    category = fields.Selection(
        [
            ("resto", "Restaurant"),
            ("hebergement", "Hébergement"),
            ("plein_air", "Plein air"),
            ("spa", "Spa / bien-être"),
            ("other", "Autre"),
        ],
        default="resto",
        required=True,
    )
    relation_type = fields.Selection(
        [
            ("direct", "Partenaire direct"),
            ("libre_service", "Inscription libre-service"),
        ],
        default="direct",
        required=True,
    )
    state = fields.Selection(
        [
            ("en_attente", "En attente"),
            ("prospected", "Prospecté"),
            ("discussing", "En discussion"),
            ("signed", "Signé"),
        ],
        default="prospected",
        required=True,
        tracking=True,
    )
    contact_name = fields.Char()
    partner_id = fields.Many2one("res.partner")
    phone = fields.Char()
    email = fields.Char()
    city = fields.Char(string="Ville")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    negotiated_rate = fields.Monetary(currency_field="currency_id")
    commission_pct = fields.Float(string="Commission (%)")
    notes = fields.Text()
