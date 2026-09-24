# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CoinsCarnetTier(models.Model):
    _name = 'coins.carnet.tier'
    _description = 'coins.carnet.tier'

    sequence = fields.Integer()
    seuil_badges = fields.Integer()
    seuil_parrainages_alternatif = fields.Integer()
    name = fields.Char()
    code = fields.Char()
    description = fields.Text()
    active = fields.Boolean()
    debloque_catalogue_vip = fields.Boolean()
    debloque_animation_premium = fields.Boolean()
    discount_percent = fields.Char()

    avantages_ids = fields.One2many('coins.carnet.tier.avantage', 'tier_id', string = 'Avantages')

class CoinsCarnetTierAvantage(models.Model):
    _name = 'coins.carnet.tier.avantage'
    _description = 'coins.carnet.tier.avantage'

    tier_id = fields.Many2one('coins.carnet.tier', required=True)
    sequence = fields.Integer()
    name = fields.Char()
    description = fields.Text()
    discount_percent = fields.Float()
