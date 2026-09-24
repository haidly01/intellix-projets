# -*- coding: utf-8 -*-
from odoo import fields, models


BOOST_KINDS = [
    ("radio", "Radio"),
    ("vedette", "Vedette"),
    ("influenceurs", "Influenceurs"),
    ("reseaux", "Réseaux"),
    ("itex", "ITEX"),
    ("driven", "Driven"),
]


class CoinsQuebecBoostRequest(models.Model):
    _name = "coins.quebec.boost.request"
    _description = "Demande de boost commerçant CQ"
    _order = "id desc"

    name = fields.Char(required=True)
    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    kind = fields.Selection(BOOST_KINDS, required=True, index=True)
    note = fields.Text()
    state = fields.Selection(
        [
            ("requested", "Demandé"),
            ("in_progress", "En cours"),
            ("done", "Traité"),
            ("cancelled", "Annulé"),
        ],
        default="requested",
        required=True,
        index=True,
    )
    activity_id = fields.Many2one("mail.activity", ondelete="set null")
    lead_id = fields.Many2one("crm.lead", string="Lead Finance", ondelete="set null")
    lead_ref = fields.Char(string="Réf. lead", copy=False)
    portal_user_id = fields.Many2one(
        "res.users",
        related="partenariat_id.portal_user_id",
        store=True,
        index=True,
    )
