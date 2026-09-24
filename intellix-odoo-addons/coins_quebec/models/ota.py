# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsQuebecChannexConfig(models.Model):
    _name = "coins.quebec.channex.config"
    _description = "Connexion Channex (Coins Québec)"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, default="Channex Québec")
    api_url = fields.Char()
    api_key = fields.Char()
    active = fields.Boolean(default=True)
    notes = fields.Text(
        default="Configuration vide — indépendante de Coins Marocain. "
        "Aucun webhook partagé."
    )


class CoinsQuebecChannexMapping(models.Model):
    _name = "coins.quebec.channex.mapping"
    _description = "Mapping propriété OTA (Coins Québec)"

    name = fields.Char(required=True)
    property_id = fields.Many2one("coins.quebec.property", required=True)
    channex_property_id = fields.Char(string="ID Channex")
    active = fields.Boolean(default=True)


class CoinsQuebecChannexCalendar(models.Model):
    _name = "coins.quebec.channex.calendar"
    _description = "Calendrier tarifs OTA (Coins Québec)"
    _inherit = ["coins.quebec.cad.mixin"]
    _order = "date desc"

    mapping_id = fields.Many2one("coins.quebec.channex.mapping", required=True)
    date = fields.Date(required=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    price = fields.Monetary(currency_field="currency_id")
    closed = fields.Boolean()


class CoinsQuebecChannexPush(models.Model):
    _name = "coins.quebec.channex.push"
    _description = "File fermeture OTA (Coins Québec)"
    _order = "id desc"

    name = fields.Char(required=True, default="Push")
    mapping_id = fields.Many2one("coins.quebec.channex.mapping")
    state = fields.Selection(
        [("draft", "Brouillon"), ("done", "Envoyé"), ("error", "Erreur")],
        default="draft",
    )
    payload = fields.Text()


class CoinsQuebecChannexRevision(models.Model):
    _name = "coins.quebec.channex.revision"
    _description = "Réservation OTA inbound (Coins Québec)"
    _inherit = ["coins.quebec.cad.mixin"]
    _order = "id desc"

    name = fields.Char(required=True)
    mapping_id = fields.Many2one("coins.quebec.channex.mapping")
    reservation_id = fields.Many2one("coins.quebec.reservation")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    amount = fields.Monetary(currency_field="currency_id")
    state = fields.Selection(
        [("new", "Nouveau"), ("imported", "Importé")], default="new"
    )
