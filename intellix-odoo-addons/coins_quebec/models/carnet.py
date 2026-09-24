# -*- coding: utf-8 -*-
from odoo import api, fields, models
import secrets


class CoinsQuebecCarnetTier(models.Model):
    _name = "coins.quebec.carnet.tier"
    _description = "Palier fidélité (Coins Québec)"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    seuil_badges = fields.Integer()
    seuil_parrainages_alternatif = fields.Integer()
    description = fields.Text()
    active = fields.Boolean(default=True)
    discount_percent = fields.Float(string="Remise (%)")
    avantages_ids = fields.One2many(
        "coins.quebec.carnet.tier.avantage", "tier_id", string="Avantages"
    )


class CoinsQuebecCarnetTierAvantage(models.Model):
    _name = "coins.quebec.carnet.tier.avantage"
    _description = "Avantage de palier (Coins Québec)"

    tier_id = fields.Many2one(
        "coins.quebec.carnet.tier", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    description = fields.Text()
    discount_percent = fields.Float()


class CoinsQuebecCarnet(models.Model):
    _name = "coins.quebec.carnet"
    _description = "Carnet voyageur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, default="Carnet")
    partner_id = fields.Many2one("res.partner", required=True)
    tier_id = fields.Many2one("coins.quebec.carnet.tier", string="Palier")
    active = fields.Boolean(default=True)
    code = fields.Char(copy=False)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = "CQ-%s" % secrets.token_hex(3).upper()
        return super().create(vals_list)


class CoinsQuebecAmbassador(models.Model):
    _name = "coins.quebec.ambassador"
    _description = "Ambassadeur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]

    name = fields.Char(required=True)
    partner_id = fields.Many2one("res.partner", required=True)
    carnet_id = fields.Many2one("coins.quebec.carnet")
    code_parrainage = fields.Char()
    statut = fields.Selection(
        [("draft", "Brouillon"), ("active", "Actif"), ("pause", "Pause")],
        default="draft",
    )
    active = fields.Boolean(default=True)
    taux_commission = fields.Float(string="Commission (%)")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    seuil_paiement_minimum = fields.Monetary(currency_field="currency_id")
    referral_ids = fields.One2many(
        "coins.quebec.ambassador.referral", "ambassador_id", string="Parrainages"
    )
    referral_count = fields.Integer(compute="_compute_referral_count")

    def _compute_referral_count(self):
        for rec in self:
            rec.referral_count = len(rec.referral_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code_parrainage"):
                vals["code_parrainage"] = "CQ-%s" % secrets.token_hex(3).upper()
        return super().create(vals_list)


class CoinsQuebecAmbassadorReferral(models.Model):
    _name = "coins.quebec.ambassador.referral"
    _description = "Parrainage (Coins Québec)"
    _inherit = ["coins.quebec.cad.mixin"]

    name = fields.Char(required=True, default="Parrainage")
    ambassador_id = fields.Many2one(
        "coins.quebec.ambassador", required=True, ondelete="cascade"
    )
    filleul_partner_id = fields.Many2one("res.partner", string="Filleul")
    reservation_id = fields.Many2one("coins.quebec.reservation")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id
    )
    montant = fields.Monetary(currency_field="currency_id")
    statut_commission = fields.Selection(
        [("pending", "En attente"), ("paid", "Payée")], default="pending"
    )
