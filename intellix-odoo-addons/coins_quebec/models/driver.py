# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsQuebecDriver(models.Model):
    _name = "coins.quebec.driver"
    _description = "Chauffeur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    partner_id = fields.Many2one("res.partner")
    phone = fields.Char()
    email = fields.Char()
    state = fields.Selection(
        [("draft", "Brouillon"), ("active", "Actif"), ("inactive", "Inactif")],
        default="draft",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True)
    rating = fields.Float()
    rib_coordonnees = fields.Char(string="RIB / virement")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    frais_par_course = fields.Monetary(currency_field="currency_id")
    solde_du_jour = fields.Monetary(currency_field="currency_id")
    reservation_ids = fields.One2many(
        "coins.quebec.reservation", "driver_id", string="Trajets"
    )
    contrat_ids = fields.One2many(
        "coins.quebec.driver.contrat", "chauffeur_id", string="Contrats"
    )
    mouvement_ids = fields.One2many(
        "coins.quebec.driver.mouvement", "chauffeur_id", string="Mouvements"
    )
    remise_ids = fields.One2many(
        "coins.quebec.driver.remise", "chauffeur_id", string="Remises"
    )


class CoinsQuebecDriverContrat(models.Model):
    _name = "coins.quebec.driver.contrat"
    _description = "Contrat chauffeur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, default="Contrat")
    chauffeur_id = fields.Many2one(
        "coins.quebec.driver", required=True, ondelete="cascade"
    )
    statut = fields.Selection(
        [
            ("brouillon", "Brouillon"),
            ("envoye", "Envoyé"),
            ("signe", "Signé"),
        ],
        default="brouillon",
        required=True,
    )
    date_signature = fields.Date()
    notes = fields.Text()


class CoinsQuebecDriverMouvement(models.Model):
    _name = "coins.quebec.driver.mouvement"
    _description = "Mouvement chauffeur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(required=True)
    chauffeur_id = fields.Many2one(
        "coins.quebec.driver", required=True, ondelete="cascade"
    )
    date = fields.Date(default=fields.Date.context_today, required=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    montant = fields.Monetary(currency_field="currency_id")
    notes = fields.Text()


class CoinsQuebecDriverRemise(models.Model):
    _name = "coins.quebec.driver.remise"
    _description = "Remise quotidienne chauffeur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "date desc"

    name = fields.Char(required=True, default="Remise")
    chauffeur_id = fields.Many2one(
        "coins.quebec.driver", required=True, ondelete="cascade"
    )
    date = fields.Date(default=fields.Date.context_today, required=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    montant = fields.Monetary(currency_field="currency_id")
    statut = fields.Selection(
        [("draft", "Brouillon"), ("done", "Remis")], default="draft"
    )
