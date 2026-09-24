# -*- coding: utf-8 -*-

from odoo import fields, models


class BabinvestConciergeStage(models.Model):
    _name = "babinvest.concierge.stage"
    _description = "Étape pipeline conciergerie Bab Invest"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    is_won = fields.Boolean(string="Étape gagnée (Compromis/Dépôt)")
    is_lost = fields.Boolean(string="Étape perdue")
    fold = fields.Boolean(
        string="Repliée par défaut au Kanban",
        help="Les étapes repliées par défaut sont typiquement les étapes gagnées ou perdues.",
    )
