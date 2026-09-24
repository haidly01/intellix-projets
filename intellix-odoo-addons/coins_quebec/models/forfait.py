# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsQuebecForfait(models.Model):
    _name = "coins.quebec.forfait"
    _description = "Forfait (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "sequence, name"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    palier = fields.Integer(string="Palier", help="Palier 1–8, comme côté Marocain.")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id, required=True
    )
    prix = fields.Monetary(currency_field="currency_id")
    description = fields.Text()
    booking_ids = fields.One2many(
        "coins.quebec.forfait.booking", "forfait_id", string="Réservations"
    )


class CoinsQuebecForfaitPartner(models.Model):
    _name = "coins.quebec.forfait.partner"
    _description = "Partenaire forfait (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True)
    partner_id = fields.Many2one("res.partner")
    phone = fields.Char()
    email = fields.Char()
    city = fields.Char()
    verdict = fields.Selection(
        [
            ("prioritaire", "Prioritaire"),
            ("ok", "OK"),
            ("veille", "Veille"),
        ],
        default="ok",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()


class CoinsQuebecForfaitBooking(models.Model):
    _name = "coins.quebec.forfait.booking"
    _description = "Réservation forfait (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "service_date desc, id desc"

    name = fields.Char(required=True, default="Réservation forfait")
    forfait_id = fields.Many2one("coins.quebec.forfait", required=True)
    partner_id = fields.Many2one("res.partner", string="Client")
    prestataire_id = fields.Many2one("coins.quebec.forfait.partner")
    service_date = fields.Date()
    status = fields.Selection(
        [
            ("prospect", "Prospect"),
            ("confirme", "Confirmé"),
            ("realise", "Réalisé"),
            ("annule", "Annulé"),
        ],
        default="prospect",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    amount = fields.Monetary(currency_field="currency_id")
    notes = fields.Text()
