# -*- coding: utf-8 -*-
from odoo import fields, models


class PaymentProviderRiad(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[
            ("charibaas", "ChariBaaS"),
            ("pay10", "Pay10"),
        ],
        ondelete={"charibaas": "set default", "pay10": "set default"},
    )
    charibaas_merchant_id = fields.Char(
        string="Identifiant marchand ChariBaaS / Pay10",
        groups="base.group_system",
        copy=False,
    )
    charibaas_api_key = fields.Char(
        string="Clé API ChariBaaS / Pay10",
        groups="base.group_system",
        copy=False,
    )
